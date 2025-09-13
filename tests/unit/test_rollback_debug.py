"""Debug test to verify rollback is working."""

import pytest
from sqlalchemy import text


class TestRollbackDebug:
    """Tests to debug rollback behavior."""

    @pytest.mark.asyncio
    async def test_create_and_check_in_transaction(self, db_context):
        """Create data and check it's visible in same transaction."""
        print("\n=== TEST: Create and check in transaction ===")
        
        # Check transaction state
        session = db_context.session
        print(f"In transaction: {session.in_transaction()}")
        
        # Get initial count
        result = await session.execute(text("SELECT COUNT(*) FROM cat_exchanges"))
        initial_count = result.scalar()
        print(f"Initial exchange count: {initial_count}")
        
        # Create an exchange
        exchange = await db_context.exchanges.create_cat_exchange(
            name="test_exchange_1",
            ohlcv_view=""
        )
        await db_context.flush()
        print(f"Created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        
        # Check count after creation
        result = await session.execute(text("SELECT COUNT(*) FROM cat_exchanges"))
        after_count = result.scalar()
        print(f"Exchange count after creation: {after_count}")
        
        # The data should be visible in the same transaction
        assert after_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_check_rollback_worked(self, db_context):
        """Check if previous test's data was rolled back."""
        print("\n=== TEST: Check rollback worked ===")
        
        session = db_context.session
        print(f"In transaction: {session.in_transaction()}")
        
        # Check if previous test's data exists
        result = await session.execute(text("SELECT COUNT(*) FROM cat_exchanges"))
        count = result.scalar()
        print(f"Exchange count in new test: {count}")
        
        # List all exchanges
        result = await session.execute(text("SELECT name FROM cat_exchanges"))
        names = [row[0] for row in result.fetchall()]
        print(f"Exchange names in database: {names}")
        
        # Should be empty if rollback worked
        assert count == 0, f"Expected 0 exchanges, found {count}. Rollback failed!"
        
    @pytest.mark.asyncio
    async def test_create_same_name_should_work(self, db_context):
        """Should be able to create same exchange name if rollback worked."""
        print("\n=== TEST: Create same name should work ===")
        
        # This should succeed if rollback worked
        exchange = await db_context.exchanges.create_cat_exchange(
            name="test_exchange_1",  # Same name as first test
            ohlcv_view=""
        )
        await db_context.flush()
        print(f"Successfully created exchange: {exchange.name} with ID {exchange.cat_ex_id}")
        
        # If we get here, rollback worked
        assert exchange.cat_ex_id is not None