"""Places and distances. A place has an id and a display name; the engine's `Scene.location` is
the display name. Distances are walking minutes along edges; any pair is reachable through the
graph (shortest path). More places can be added lazily with `add_place`."""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

UNLINKED_MINUTES = 60  # a place added without links is this far from everything


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    note: str = ""
    to: str = ""  # "where to" with its preposition and case: «до брами», «на ринок»; "" = not known


@dataclass
class WorldMap:
    places: dict[str, Place] = field(default_factory=dict)
    edges: dict[str, dict[str, int]] = field(default_factory=dict)

    def add_place(self, place: Place, links: dict[str, int] | None = None) -> Place:
        self.places[place.id] = place
        self.edges.setdefault(place.id, {})
        for other, minutes in (links or {}).items():
            if other not in self.places:
                raise KeyError(f"unknown place {other!r}")
            self.edges[place.id][other] = minutes
            self.edges[other][place.id] = minutes
        return place

    def resolve(self, ref: str) -> Place | None:
        """A place by id or display name (case-insensitive); None if unknown."""
        if ref in self.places:
            return self.places[ref]
        low = ref.strip().lower()
        for p in self.places.values():
            if p.name.lower() == low:
                return p
        return None

    def name(self, place_id: str) -> str:
        return self.places[place_id].name if place_id in self.places else place_id

    def minutes(self, a: str, b: str) -> int:
        """Shortest walking time between two places (0 for the same place)."""
        if a == b:
            return 0
        if a not in self.places or b not in self.places:
            return UNLINKED_MINUTES
        dist = {a: 0}
        heap = [(0, a)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == b:
                return d
            if d > dist.get(u, 1 << 30):
                continue
            for v, w in self.edges.get(u, {}).items():
                nd = d + w
                if nd < dist.get(v, 1 << 30):
                    dist[v] = nd
                    heapq.heappush(heap, (nd, v))
        return UNLINKED_MINUTES * 4  # not connected: far


def vizima() -> WorldMap:
    """The pilot map (task 17). Distances are rough walking minutes inside the city."""
    m = WorldMap()
    m.add_place(Place("tavern", "корчма «Під Лисом»", "evening crowd, merchants and soldiers", to="до корчми «Під Лисом»"))
    m.add_place(Place("market", "ринок", "the main square market", to="на ринок"), {"tavern": 10})
    m.add_place(Place("gate", "брама", "the city gate", to="до брами"), {"market": 12, "tavern": 8})
    m.add_place(Place("guardhouse", "кордегардія біля палацу", "the guard barracks by the palace", to="до кордегардії біля палацу"),
                {"market": 15})
    m.add_place(Place("palace", "старий палац", "the old palace", to="до старого палацу"), {"guardhouse": 3})
    m.add_place(Place("lake", "берег озера", "the lake shore outside the walls", to="до берега озера"),
                {"gate": 25, "palace": 20})
    return m
