#!/usr/bin/env python3
"""
Import Validation Script for fullon_ticker_service

This script validates that the basic package structure is correct
and imports work as expected. This is a lightweight test that doesn't
require the full fullon ecosystem to be set up.
"""

import sys
import asyncio
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


def test_imports():
    """Test that all main classes can be imported."""
    print("🔍 Testing imports...")
    
    try:
        from fullon_ticker_service import TickerDaemon, ExchangeHandler, TickerManager
        print("✅ All main classes imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


async def test_basic_functionality():
    """Test basic functionality of stub classes."""
    print("\n🔍 Testing basic functionality...")
    
    try:
        from fullon_ticker_service import TickerDaemon, ExchangeHandler, TickerManager
        
        # Test TickerDaemon
        daemon = TickerDaemon()
        assert daemon.get_status().value == "stopped"
        assert not daemon.is_running()
        
        # Test basic lifecycle (should work with stubs)
        await daemon.start()
        assert daemon.is_running()
        
        await daemon.stop()
        assert not daemon.is_running()
        
        print("✅ TickerDaemon basic lifecycle works")
        
        # Test ExchangeHandler
        handler = ExchangeHandler("binance", ["BTC/USDT", "ETH/USDT"])
        assert handler.exchange_name == "binance"
        assert handler.symbols == ["BTC/USDT", "ETH/USDT"]
        assert handler.get_status().value == "disconnected"
        
        print("✅ ExchangeHandler basic functionality works")
        
        # Test TickerManager
        manager = TickerManager()
        stats = manager.get_ticker_stats()
        assert stats["total_tickers"] == 0
        assert stats["exchanges"] == []
        
        print("✅ TickerManager basic functionality works")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        return False


async def test_async_patterns():
    """Test that async patterns work correctly."""
    print("\n🔍 Testing async patterns...")
    
    try:
        from fullon_ticker_service import TickerDaemon, ExchangeHandler
        
        # Test multiple concurrent operations
        daemon1 = TickerDaemon()
        daemon2 = TickerDaemon()
        
        # Start both concurrently
        await asyncio.gather(
            daemon1.start(),
            daemon2.start()
        )
        
        assert daemon1.is_running()
        assert daemon2.is_running()
        
        # Stop both concurrently
        await asyncio.gather(
            daemon1.stop(),
            daemon2.stop()
        )
        
        assert not daemon1.is_running()
        assert not daemon2.is_running()
        
        print("✅ Async patterns work correctly")
        return True
        
    except Exception as e:
        print(f"❌ Async patterns test failed: {e}")
        return False


def test_example_imports():
    """Test that examples can import the classes they need."""
    print("\n🔍 Testing example import compatibility...")
    
    try:
        # Test the specific imports that examples use
        from fullon_ticker_service import TickerDaemon
        
        # Verify the classes have the methods examples expect
        daemon = TickerDaemon()
        
        # Check methods exist (examples rely on these)
        assert hasattr(daemon, 'start')
        assert hasattr(daemon, 'stop') 
        assert hasattr(daemon, 'is_running')
        assert hasattr(daemon, 'get_status')
        assert hasattr(daemon, 'get_health')
        
        print("✅ Example import compatibility confirmed")
        return True
        
    except Exception as e:
        print(f"❌ Example import compatibility failed: {e}")
        return False


async def main():
    """Run all validation tests."""
    print("🚀 FULLON TICKER SERVICE - IMPORT VALIDATION")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Basic Functionality", test_basic_functionality),
        ("Async Patterns", test_async_patterns),
        ("Example Compatibility", test_example_imports)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name}...")
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
                
            if result:
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
                
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")
    
    print("\n" + "=" * 50)
    print("📊 VALIDATION RESULTS")
    print("=" * 50)
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED! ({passed}/{total})")
        print("✅ Import structure is working correctly")
        print("✅ Examples should be able to import classes")
        print("✅ Basic functionality is operational")
        print("✅ Ready for full implementation")
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total})")
        print("⚠️ Import structure needs fixes")
        failed = total - passed
        print(f"📋 {failed} test(s) need attention")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)