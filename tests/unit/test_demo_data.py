"""
Unit tests for demo_data ORM attribute access patterns.

Tests that demo_data.py correctly uses ORM object attributes
instead of dictionary-style access patterns.
"""

import pytest
from fullon_orm.models import Exchange


class TestDemoDataORMAccess:
    """Test ORM attribute access in demo_data module."""

    @pytest.mark.asyncio
    async def test_exchange_orm_object_no_dict_methods(self):
        """Test that Exchange ORM objects don't have dictionary methods."""
        exchange = Exchange()
        exchange.ex_id = 1
        exchange.cat_ex_id = 1
        exchange.name = "test_exchange"
        exchange.uid = 1

        # Verify Exchange objects don't have dictionary methods
        assert not hasattr(exchange, 'get'), "Exchange should not have 'get' method"
        assert not hasattr(exchange, 'keys'), "Exchange should not have 'keys' method"
        assert not hasattr(exchange, 'items'), "Exchange should not have 'items' method"

        # Verify correct attribute access
        assert exchange.ex_id == 1
        assert exchange.cat_ex_id == 1
        assert exchange.name == "test_exchange"
        assert exchange.uid == 1

        # Verify wrong attribute names don't exist
        assert not hasattr(exchange, 'ex_name'), "Exchange should use 'name', not 'ex_name'"
        assert not hasattr(exchange, 'ex_named'), "Exchange should use 'name', not 'ex_named'"

    @pytest.mark.asyncio
    async def test_demo_data_imports_successfully(self):
        """Test that demo_data can be imported and functions are accessible."""
        # This test verifies that our fixes don't break the module import
        try:
            from examples.demo_data import (
                install_exchanges_internal,
                install_symbols_internal,
                install_admin_user_internal,
            )
            # If import succeeds, the module syntax is correct
            assert callable(install_exchanges_internal)
            assert callable(install_symbols_internal)
            assert callable(install_admin_user_internal)
        except ImportError as e:
            pytest.fail(f"Failed to import demo_data functions: {e}")
        except AttributeError as e:
            pytest.fail(f"demo_data has ORM attribute access issues: {e}")
