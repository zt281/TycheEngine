"""Test script to verify static_data module query functionality."""

import sys
sys.path.insert(0, 'src')

from tyche.module import TycheModule
from tyche.types import Endpoint


class TestModule(TycheModule):
    def __init__(self):
        super().__init__(
            engine_endpoint=Endpoint('127.0.0.1', 5555),
            family_name='test_query',
        )


def main():
    mod = TestModule()
    mod.start()

    try:
        # Query instruments for ag@SHFE
        result = mod.request_event(
            'query_instruments',
            {'exchange_id': 'SHFE', 'product_id': 'ag'},
            timeout=5.0
        )
        print('Query result keys:', list(result.keys()) if hasattr(result, 'keys') else type(result))

        if 'result' in result:
            inner = result['result']
            if 'instruments' in inner:
                instruments = inner['instruments']
                print(f'Found {len(instruments)} instruments')
                for inst in instruments[:5]:
                    print(f'  - {inst.get("InstrumentID", "?")}')
            else:
                print('Inner result keys:', list(inner.keys()))
                print('Inner result:', inner)
        elif 'error' in result:
            print('Error:', result['error'])
        else:
            print('Result:', result)

    except Exception as e:
        print(f'Query failed: {e}')
        import traceback
        traceback.print_exc()
    finally:
        mod.stop()


if __name__ == '__main__':
    main()
