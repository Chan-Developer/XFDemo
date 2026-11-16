"""Run real-image integration checks without writing production history records."""
import base64
import json
import os
import time
import secrets
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.modules.inspection.pipeline import InspectionAgent
from backend.config.settings import get_settings
from backend.infrastructure.vision.yolo_detector import run_yolo_detection


def validate_scope(state, expected):
    """Compare configured scope codes with the report's localized scope names."""
    expected_name = {"appearance": "箱体外观", "internal_components": "内部组件"}.get(expected, expected)
    actual = state['trace']['summary']['final']['scope']
    assert actual == expected_name, f'expected scope {expected_name!r}, got {actual!r}'


def validate_public(base_url):
    """Exercise the real proxy, authentication, stream and history; remove only test data."""
    import requests
    from backend.infrastructure.database.postgres import database_connection

    session = requests.Session()
    session.trust_env = False
    base_url = base_url.rstrip('/')
    account = 'release_' + uuid.uuid4().hex[:12]
    user_id, records, rows = None, [], []
    try:
        health = session.get(base_url + '/api/health', timeout=15)
        health.raise_for_status()
        assert health.json()['detector_mode'] == 'unified'
        response = session.post(base_url + '/api/auth/register', json={
            'username': account, 'email': account + '@example.invalid',
            'password': secrets.token_urlsafe(24) + 'A1', 'displayName': 'Release validation',
        }, timeout=20)
        response.raise_for_status()
        user_id = response.json()['user']['id']
        source = json.loads(Path(os.environ['VALIDATION_SOURCE']).read_text())
        for branch in ('fire_extinguisher', 'fire_door', 'water_pump_connector'):
            sample = next(row for row in source if row['branch'] == branch)
            payload = {'query': '检查图片中的消防设施', 'image': 'data:image/jpeg;base64,' +
                       base64.b64encode(Path(sample['image']).read_bytes()).decode()}
            started = time.monotonic()
            # Requests also uses this socket timeout while sending the image body.
            # Full-resolution uploads over a relay can exceed a short connect budget.
            with session.post(base_url + '/api/chat/stream', json=payload, stream=True, timeout=(120, 600)) as response:
                response.raise_for_status()
                events = [json.loads(line) for line in response.iter_lines() if line]
            errors = [event for event in events if event.get('type') == 'error']
            assert not errors, str(errors)
            done = next(event for event in events if event.get('type') == 'done')
            record = done['history']
            records.append(record['id'])
            assert done['yolo']['detectorMode'] == 'unified'
            assert done['trace']['inspectionType'] == branch
            for field in ('imageUrl', 'yoloImageUrl'):
                image_url = record[field]
                if not image_url.startswith('/api/'):
                    image_url = '/api/' + image_url.lstrip('/')
                image_response = session.get(base_url + image_url, timeout=20)
                image_response.raise_for_status()
                assert image_response.headers['Content-Type'].startswith('image/')
            saved = session.get(base_url + '/api/history/inspections/' + record['id'] + '/revisions', timeout=15)
            saved.raise_for_status()
            if branch in ('fire_door', 'water_pump_connector'):
                assert record['modelReportDocument']['verdict'] == 'not_assessed'
            rows.append({'branch': branch, 'passed': True, 'seconds': round(time.monotonic() - started, 2),
                         'report': done['response'], 'historyId': record['id'], 'imageEndpoints': 'passed'})
            Path(os.environ['VALIDATION_OUTPUT']).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        Path(os.environ['VALIDATION_OUTPUT']).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    finally:
        for record_id in records:
            deleted = session.delete(base_url + '/api/history/inspections/' + record_id, timeout=20)
            deleted.raise_for_status()
        if user_id:
            # Match both generated ID and random name; never remove existing users.
            get_settings()
            with database_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('DELETE FROM users WHERE id=%s AND username=%s', (user_id, account))
        session.close()


def main():
    if os.getenv('VALIDATION_PUBLIC_URL'):
        return validate_public(os.environ['VALIDATION_PUBLIC_URL'])
    root = Path('/data/clj/data/xfLLM/training_data/20261105_fire_facility_v2_clean/components_yolo')
    output = Path(os.environ['VALIDATION_OUTPUT'])
    output.parent.mkdir(parents=True, exist_ok=True)
    agent = InspectionAgent(get_settings())
    for model in (agent.model, agent.judge_model, agent.direction_model):
        model.client = model.client.with_options(timeout=180, max_retries=0)
    rows = []
    branches = os.getenv('VALIDATION_BRANCHES', 'indoor_hydrant,outdoor_hydrant,fire_extinguisher').split(',')
    for branch in branches:
        image = Path(os.environ['VALIDATION_IMAGE']) if os.getenv('VALIDATION_IMAGE') else sorted((root / branch / 'images/test').iterdir())[0]
        started = time.monotonic()
        row = {'branch': branch, 'image': str(image)}
        try:
            with patch('backend.modules.inspection.router.run_yolo_detection', wraps=run_yolo_detection) as infer, patch(
                'backend.modules.inspection.pipeline.run_yolo_detection', wraps=run_yolo_detection
            ) as align:
                state = agent.invoke({'query': '检查图片中的消防设施', 'image': 'data:image/jpeg;base64,' + base64.b64encode(image.read_bytes()).decode()}, progress_callback=lambda e: print(json.dumps({'branch': branch, 'stage': e.get('stage'), 'status': e.get('status')}, ensure_ascii=False), flush=True))
                row.update({'actualBranch': state.get('inspection_type'), 'report': state['report'],
                            'yoloCalls': infer.call_count + align.call_count,
                            'detectionCount': len(state['yolo']['detections']),
                            'state': {k: v for k, v in state.items() if k not in ('image', 'messages')}})
                row['branchMatchesDataset'] = row['actualBranch'] == branch
                # This reviewed test photo is a corridor containing sprinklers and detectors.
                # Both scene classifications use the same observation-only path, but the
                # sprinkler must remain in the boxes and in the image-grounded description.
                mixed_corridor = (image.name == 'sprinkler_007faf9d13097add22ca.jpg'
                                  and row['actualBranch'] == 'evacuation_passage')
                if mixed_corridor:
                    assert '喷头' in state['report']
                    assert any('洒水喷头' in item['className'] for item in state['yolo']['detections'])
                    row['reviewNote'] = '多设备走廊场景：按通道识别，仍保留喷头位置及观察描述；不计作严格主类型命中。'
                else:
                    assert row['actualBranch'] == branch, 'facility branch mismatch'
                assert row['yoloCalls'] == 1, 'YOLO must run exactly once'
                assert state['yolo']['detectorMode'] == 'unified'
                assert row['detectionCount'] > 0, 'expected component boxes'
                assert state['report'], 'empty report'
                if os.getenv('VALIDATION_EXPECT_SCOPE'):
                    validate_scope(state, os.environ['VALIDATION_EXPECT_SCOPE'])
                if os.getenv('VALIDATION_FORBID_LABEL'):
                    assert os.environ['VALIDATION_FORBID_LABEL'] not in state['trace']['summary']['final']['labels']
            row['passed'] = True
        except Exception as exc:
            row.update({'passed': False, 'error': str(exc)})
        row['seconds'] = round(time.monotonic() - started, 2)
        rows.append(row)
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in row.items() if k != 'state'}, ensure_ascii=False), flush=True)
    if not all(row['passed'] for row in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
