import pytest
import asyncio


@pytest.mark.asyncio
async def test_trivial_async():
    await asyncio.sleep(0.01)
    assert True
