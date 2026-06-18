import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django_scopes import scopes_disabled
from pytest_factoryboy import LazyFixture, register

from cookbook.models import InventoryEntry, InventoryLog
from cookbook.tests.factories import (FoodFactory, IngredientFactory, InventoryEntryFactory, RecipeFactory, StepFactory)

LIST_URL = 'api:inventoryentry-list'
DETAIL_URL = 'api:inventoryentry-detail'
VERIFY_URL = 'api:inventoryentry-verify'

register(InventoryEntryFactory, 'entry_1', space=LazyFixture('space_1'))


@pytest.fixture
def entry_stale(space_1, u1_s1):
    with scopes_disabled():
        e = InventoryEntryFactory(space=space_1)
        e.last_verified_at = timezone.now() - timedelta(days=100)
        e.save()
        return e


# ---------------------------------------------------------------- is_stale model property


def test_is_stale_uses_space_default(space_1, u1_s1):
    with scopes_disabled():
        space_1.pantry_default_verification_days = 7
        space_1.save()
        e = InventoryEntryFactory(space=space_1)

        e.last_verified_at = timezone.now() - timedelta(days=3)
        assert e.is_stale is False

        e.last_verified_at = timezone.now() - timedelta(days=30)
        assert e.is_stale is True


def test_food_interval_overrides_space_default(space_1, u1_s1):
    with scopes_disabled():
        space_1.pantry_default_verification_days = 365
        space_1.save()
        e = InventoryEntryFactory(space=space_1)
        e.food.verification_interval_days = 2
        e.food.save()

        e.last_verified_at = timezone.now() - timedelta(days=5)
        assert e.is_stale is True


@pytest.mark.parametrize('food_interval, space_default', [(0, 14), (None, 0)])
def test_never_stale(space_1, u1_s1, food_interval, space_default):
    # food interval of 0 OR a space default of 0 (with no food override) means "never goes stale"
    with scopes_disabled():
        space_1.pantry_default_verification_days = space_default
        space_1.save()
        e = InventoryEntryFactory(space=space_1)
        e.food.verification_interval_days = food_interval
        e.food.save()

        e.last_verified_at = timezone.now() - timedelta(days=9999)
        assert e.is_stale is False


def test_missing_verification_is_stale(space_1, u1_s1):
    with scopes_disabled():
        space_1.pantry_default_verification_days = 7
        space_1.save()
        e = InventoryEntryFactory(space=space_1)
        e.last_verified_at = None
        assert e.is_stale is True


# ---------------------------------------------------------------- verify action


def test_verify_stamps_timestamp_and_logs(u1_s1, entry_stale):
    url = reverse(VERIFY_URL, args=[entry_stale.id])
    r = u1_s1.post(url)
    assert r.status_code == 200

    body = json.loads(r.content)
    assert body['is_stale'] is False
    assert body['last_verified_at'] is not None

    with scopes_disabled():
        entry = InventoryEntry.objects.get(id=entry_stale.id)
        assert entry.last_verified_at > timezone.now() - timedelta(minutes=1)
        # verification is recorded in the audit log without mutating amount/location
        log = InventoryLog.objects.filter(entry=entry, booking_type=InventoryLog.B_CHECK)
        assert log.count() == 1
        assert log.first().old_amount == entry.amount
        assert log.first().new_amount == entry.amount


def test_verify_requires_authentication(a_u, entry_stale):
    url = reverse(VERIFY_URL, args=[entry_stale.id])
    r = a_u.post(url)
    assert r.status_code == 403


# ---------------------------------------------------------------- stale list filter


def _recipe_with_food(space, food):
    # build a recipe whose single step uses exactly the given food
    ingredient = IngredientFactory(food=food, space=space)
    step = StepFactory(space=space, ingredients=[ingredient], ingredients__count=0)
    recipe = RecipeFactory(space=space, steps__count=0)
    recipe.steps.add(step)
    return recipe


# ---------------------------------------------------------------- recipes list filter


def test_recipes_filter(u1_s1, space_1):
    with scopes_disabled():
        food = FoodFactory(space=space_1)
        other_food = FoodFactory(space=space_1)
        recipe = _recipe_with_food(space_1, food)
        wanted = InventoryEntryFactory(space=space_1, food=food)
        unrelated = InventoryEntryFactory(space=space_1, food=other_food)

    r = u1_s1.get(f'{reverse(LIST_URL)}?recipes={recipe.id}')
    assert r.status_code == 200
    returned_ids = {e['id'] for e in json.loads(r.content)['results']}
    assert wanted.id in returned_ids
    assert unrelated.id not in returned_ids


def test_recipes_filter_with_stale(u1_s1, space_1):
    with scopes_disabled():
        space_1.pantry_default_verification_days = 7
        space_1.save()
        food = FoodFactory(space=space_1)
        recipe = _recipe_with_food(space_1, food)
        fresh = InventoryEntryFactory(space=space_1, food=food)
        fresh.last_verified_at = timezone.now()
        fresh.save()
        stale = InventoryEntryFactory(space=space_1, food=food)
        stale.last_verified_at = timezone.now() - timedelta(days=30)
        stale.save()

    returned_ids = {e['id'] for e in json.loads(u1_s1.get(f'{reverse(LIST_URL)}?recipes={recipe.id}&stale=true').content)['results']}
    assert stale.id in returned_ids
    assert fresh.id not in returned_ids


def test_recipes_filter_invalid(u1_s1, space_1):
    with scopes_disabled():
        InventoryEntryFactory(space=space_1)
    r = u1_s1.get(f'{reverse(LIST_URL)}?recipes=abc')
    assert r.status_code == 200
    assert json.loads(r.content)['results'] == []


def test_stale_filter(u1_s1, space_1):
    with scopes_disabled():
        space_1.pantry_default_verification_days = 7
        space_1.save()
        fresh = InventoryEntryFactory(space=space_1)
        fresh.last_verified_at = timezone.now()
        fresh.save()
        stale = InventoryEntryFactory(space=space_1)
        stale.last_verified_at = timezone.now() - timedelta(days=30)
        stale.save()

    r = u1_s1.get(f'{reverse(LIST_URL)}?stale=true')
    assert r.status_code == 200
    returned_ids = {e['id'] for e in json.loads(r.content)['results']}
    assert stale.id in returned_ids
    assert fresh.id not in returned_ids
