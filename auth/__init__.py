"""Shared authentication for the Tripletex API."""

from auth.tripletex import (
    CompanyRegistry,
    TripletexAuthAsync,
    TripletexAuthSync,
    load_tripletex_companies,
    tripletex_get_async,
    tripletex_get_sync,
)

__all__ = [
    "TripletexAuthSync",
    "TripletexAuthAsync",
    "CompanyRegistry",
    "load_tripletex_companies",
    "tripletex_get_sync",
    "tripletex_get_async",
]
