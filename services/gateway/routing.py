"""Gateway routing with A/B testing support."""

import json
import random
from typing import Optional, Dict
from dataclasses import dataclass
from opentelemetry import trace


@dataclass
class RouteConfig:
    """Configuration for a single route."""
    url: str
    timeout_ms: int
    ab_variants: Optional[Dict[str, Dict]] = None  # {variant: {weight: int}}


class Router:
    """Routes requests to team services with A/B support."""

    def __init__(self, route_table_json: str):
        self.routes: Dict[str, RouteConfig] = {}
        self._parse_route_table(route_table_json)
        self.tracer = trace.get_tracer(__name__)

    def _parse_route_table(self, json_str: str):
        """Parse route table from JSON config."""
        config = json.loads(json_str)
        for team, settings in config.items():
            self.routes[team] = RouteConfig(
                url=settings["url"],
                timeout_ms=settings.get("timeout_ms", 30000),
                ab_variants=settings.get("ab_variants")
            )

    def get_route(self, team: str) -> Optional[RouteConfig]:
        """Get route configuration for a team."""
        return self.routes.get(team)

    def select_variant(self, team: str) -> Optional[str]:
        """
        Select A/B variant based on configured weights.

        Returns:
            Selected variant name, or None if no A/B configured
        """
        route = self.routes.get(team)
        if not route or not route.ab_variants:
            return None

        # Calculate total weight
        variants = route.ab_variants
        total_weight = sum(v.get("weight", 0) for v in variants.values())
        if total_weight == 0:
            return None

        # Random selection
        rand = random.randint(1, total_weight)
        cumulative = 0
        for variant_name, variant_config in variants.items():
            cumulative += variant_config.get("weight", 0)
            if rand <= cumulative:
                return variant_name

        return list(variants.keys())[0]  # Fallback to first variant

    def get_available_teams(self) -> list:
        """Return list of available team routes."""
        return list(self.routes.keys())
