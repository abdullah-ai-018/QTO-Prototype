"""Dynamic Trade Registry for extensible trade engine lookup.
Allows adding future trades (Framing, Insulation, Siding, Tile, MEP, etc.)
without modifying orchestrator or existing trade engines.
"""

from typing import Dict, Type, Optional
from app.models.enums import TradeKey
from app.trades.base import TradeEngine


class TradeRegistry:
    """Registry managing available TradeEngine implementations."""

    _registry: Dict[TradeKey, Type[TradeEngine]] = {}

    @classmethod
    def register(cls, trade_key: TradeKey, engine_cls: Type[TradeEngine]) -> None:
        """Register a new trade engine class."""
        cls._registry[trade_key] = engine_cls

    @classmethod
    def get_engine_class(cls, trade_key: TradeKey) -> Optional[Type[TradeEngine]]:
        """Get the engine class registered for a trade key."""
        return cls._registry.get(trade_key)

    @classmethod
    def create_engine(cls, trade_key: TradeKey, **kwargs) -> Optional[TradeEngine]:
        """Instantiate the engine for a trade key."""
        engine_cls = cls.get_engine_class(trade_key)
        if engine_cls is None:
            return None
        return engine_cls(**kwargs)

    @classmethod
    def list_trades(cls) -> list[TradeKey]:
        """List all registered trade keys."""
        return list(cls._registry.keys())


# Self-register initial 4 trades
def _register_builtin_trades():
    from app.trades.drywall import DrywallEngine
    from app.trades.painting import PaintingEngine
    from app.trades.flooring import FlooringEngine
    from app.trades.roofing import EnhancedRoofingEngine

    TradeRegistry.register(TradeKey.DRYWALL, DrywallEngine)
    TradeRegistry.register(TradeKey.PAINTING, PaintingEngine)
    TradeRegistry.register(TradeKey.FLOORING, FlooringEngine)
    TradeRegistry.register(TradeKey.ROOFING, EnhancedRoofingEngine)


_register_builtin_trades()

# Backward-compatibility instance dictionary
TRADE_ENGINES: Dict[TradeKey, TradeEngine] = {
    trade_key: engine_cls() for trade_key, engine_cls in TradeRegistry._registry.items()
}
