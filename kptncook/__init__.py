"""
kptncook is a little command line utility to download
new recipes.
"""

import sys
from datetime import date

import httpx
import typer
from rich import print as rprint
from rich.pretty import pprint
from rich.prompt import Prompt

from .api import KptnCookClient
from .config import settings
from .mealie import MealieApiClient, kptncook_to_mealie
from .models import Recipe
from .repositories import RecipeRepository

__all__ = ["list_http"]

__version__ = "0.0.5"
cli = typer.Typer()


@cli.command(name="http")
def list_http():
    """
    List all recipes for today the kptncook site.
    """
    client = KptnCookClient()
    all_recipes = client.list_today()
    for recipe in all_recipes:
        pprint(recipe)


@cli.command(name="save_todays_recipes")
def save_todays_recipes():
    """
    Save recipes for today from kptncook site.
    """
    fs_repo = RecipeRepository(settings.root)
    if fs_repo.needs_to_be_synced(date.today()):
        client = KptnCookClient()
        fs_repo.add_list(client.list_today())


def get_mealie_client() -> MealieApiClient:
    client = MealieApiClient(settings.mealie_url)
    client.login(settings.mealie_username, settings.mealie_password)
    return client


def get_kptncook_recipes_from_mealie(client):
    recipes = client.get_all_recipes()
    recipes_with_details = []
    for recipe in recipes:
        recipes_with_details.append(client.get_via_slug(recipe.slug))
    kptncook_recipes = [
        r for r in recipes_with_details if r.extras.get("source") == "kptncook"
    ]
    return kptncook_recipes


def get_kptncook_recipes_from_repository() -> list[Recipe]:
    fs_repo = RecipeRepository(settings.root)
    recipes = []
    for repo_recipe in fs_repo.list():
        recipes.append(Recipe.parse_obj(repo_recipe.data))
    return recipes


@cli.command(name="sync_with_mealie")
def sync_with_mealie():
    """
    Sync locally saced recipes with mealie.
    """
    try:
        client = get_mealie_client()
    except Exception as e:
        rprint(f"Could not login to mealie: {e}")
        sys.exit(1)
    kptncook_recipes_from_mealie = get_kptncook_recipes_from_mealie(client)
    recipes = get_kptncook_recipes_from_repository()
    kptncook_recipes_from_repository = [kptncook_to_mealie(r) for r in recipes]
    ids_in_mealie = {r.extras["kptncook_id"] for r in kptncook_recipes_from_mealie}
    ids_from_api = {r.extras["kptncook_id"] for r in kptncook_recipes_from_repository}
    ids_to_add = ids_from_api - ids_in_mealie
    recipes_to_add = []
    for recipe in kptncook_recipes_from_repository:
        if recipe.extras.get("kptncook_id") in ids_to_add:
            recipes_to_add.append(recipe)
    created_slugs = []
    for recipe in recipes_to_add:
        try:
            created = client.create_recipe(recipe)
            created_slugs.append(created.slug)
        except httpx.HTTPStatusError as e:
            if (
                e.response.json().get("detail", {}).get("message")
                == "Recipe already exists"
            ):
                continue
    rprint(f"Created {len(created_slugs)} recipes")


@cli.command(name="sync")
def sync():
    """
    Fetch recipes for today from api, save them to disk and sync with mealie
    afterwards.
    """
    save_todays_recipes()
    sync_with_mealie()


@cli.command(name="favsync")
def favsync():
    """
    Sync favorite recipes from kptncook with mealie.
    """
    if settings.kptncook_access_token is None:
        print("Please set KPTNCOOK_ACCESS_TOKEN in your environment or .env file")
        sys.exit(1)
    client = KptnCookClient()
    favorites = client.list_favorites()
    rprint(favorites)
    favorites = client.get_by_oids(favorites)
    print(len(favorites))


@cli.command(name="kptncook_access_token")
def get_access_token():
    """
    Get access token for kptncook.
    """
    username = Prompt.ask("Enter your kptncook email address")
    password = Prompt.ask("Enter your kptncook password", password=True)
    client = KptnCookClient()
    access_token = client.get_access_token(username, password)
    rprint("your access token: ", access_token)


@cli.command(name="list_recipes")
def list_recipes():
    """
    List all locally saved recipes.
    """
    recipes = get_kptncook_recipes_from_repository()
    for recipe in recipes:
        rprint(recipe.localized_title.de, recipe.id.oid)


if __name__ == "__main__":
    cli()
