from __future__ import annotations

from pathlib import Path

from rlm_research_planner.domain.models import PlayerState
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.services.catalog_planning import CatalogResearchPlanner


def _catalog_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "data"
        / "research"
        / "catalog.json"
    )


def test_catalog_contains_every_current_category_and_known_tree_item() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    assert len(categories) == 16
    assert sum(len(category.nodes) for category in categories) == 399
    assert {category.category_id for category in categories} == {
        "economy",
        "defense",
        "military",
        "monster_hunt",
        "upgrade_defenses",
        "upgrade_military",
        "army_leadership",
        "military_command",
        "familiars",
        "familiar_battles",
        "sigils",
        "wonder_battles",
        "gear",
        "advanced_wonder_battles",
        "mana_awakening",
        "guild_duel",
    }
    guild_duel = next(
        category for category in categories if category.category_id == "guild_duel"
    )
    assert guild_duel.license_name == "Public gameplay reference (facts transcribed)"
    assert guild_duel.license_url == ""


def test_catalog_economy_merges_verified_screen_facts() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    economy = next(item for item in categories if item.category_id == "economy")
    assert len(economy.nodes) == 9
    assert len(economy.edges) == 10
    construction = economy.node_by_id()["economy_construction_speed"]
    assert construction.localized_name("ja-JP") == "建設速度"
    assert construction.max_level == 10
    weight = economy.node_by_id()["economy_weight_training_i"]
    harvesting = economy.node_by_id()["economy_resource_harvesting_i"]
    gem = next(node for node in economy.nodes if node.localized_name("en-US") == "Gem Harvesting I")
    assert (weight.row, weight.column, weight.max_level) == (2, 0, 10)
    assert (harvesting.row, harvesting.column, harvesting.max_level) == (2, 2, 10)
    assert (gem.row, gem.column, gem.max_level) == (3, 1, 10)
    assert gem.localized_name("ja-JP") == "ジェム採掘I"


def test_sigils_helmet_sigil_has_complete_level_one_costs() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    sigils = next(item for item in categories if item.category_id == "sigils")
    helmet = sigils.node_by_id()["sigils_helmet_sigil"].level_data(1)
    assert helmet is not None
    assert helmet.base_time_seconds == 5_171_460
    assert helmet.technolabe_count == 2
    assert helmet.power == 544_024
    assert helmet.costs_verified is True
    assert helmet.costs == {
        "food": 8_137_320,
        "stone": 4_068_660,
        "timber": 4_068_660,
        "ore": 1_356_220,
        "gold": 3_904_320,
        "ancient_tomes": 96,
    }
    assert {
        (requirement.research_id, requirement.level)
        for requirement in helmet.requirements
    } == {
        ("sigils_leadership_infantry_def_i", 8),
        ("sigils_leadership_siege_def_i", 8),
        ("sigils_leadership_ranged_def_i", 8),
        ("sigils_leadership_cavalry_def_i", 8),
    }


def test_military_uses_screen_shaped_shared_connection_buses() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    military = next(item for item in categories if item.category_id == "military")
    assert len(military.connection_groups) == 25
    t3_to_army_offense = next(
        group
        for group in military.connection_groups
        if len(group.prerequisite_ids) == 4
        and group.research_ids == ("military_army_offense_i",)
    )
    assert set(t3_to_army_offense.prerequisite_ids) == {
        "military_royal_guard",
        "military_fire_trebuchet",
        "military_stealth_sniper",
        "military_royal_cavalry",
    }
    army_side_group = next(
        group
        for group in military.connection_groups
        if group.prerequisite_ids == ("military_army_offense_i",)
        and len(group.research_ids) == 2
    )
    assert set(army_side_group.research_ids) == {
        "military_army_defense_i",
        "military_army_health_i",
    }
    army_to_t4 = next(
        group
        for group in military.connection_groups
        if group.prerequisite_ids == ("military_army_offense_i",)
        and len(group.research_ids) == 4
    )
    assert set(army_to_t4.research_ids) == {
        "military_heroic_fighter",
        "military_destroyer",
        "military_heroic_cannoneer",
        "military_ancient_drake_rider",
    }
    direct_edges = {
        (edge.prerequisite_id, edge.research_id) for edge in military.edges
    }
    assert direct_edges == {
        (prerequisite_id, research_id)
        for group in military.connection_groups
        for prerequisite_id in group.prerequisite_ids
        for research_id in group.research_ids
    }
    assert {
        edge
        for edge in direct_edges
        if edge[0] in {
            "military_army_defense_i",
            "military_army_health_i",
        }
    } == set()
    nodes = military.node_by_id()
    same_row_connections = {
        (prerequisite_id, research_id)
        for group in military.connection_groups
        for prerequisite_id in group.prerequisite_ids
        for research_id in group.research_ids
        if nodes[research_id].row == nodes[prerequisite_id].row
    }
    assert same_row_connections == {
        ("military_army_offense_i", "military_army_defense_i"),
        ("military_army_offense_i", "military_army_health_i"),
    }
    assert all(
        nodes[research_id].row - nodes[prerequisite_id].row in {0, 1}
        for group in military.connection_groups
        for prerequisite_id in group.prerequisite_ids
        for research_id in group.research_ids
    )
    connected_children = {
        research_id
        for group in military.connection_groups
        for research_id in group.research_ids
    }
    connected_parents = {
        prerequisite_id
        for group in military.connection_groups
        for prerequisite_id in group.prerequisite_ids
    }
    assert connected_children == {node.id for node in military.nodes if node.row > 0}
    assert connected_parents == {
        node.id
        for node in military.nodes
        if node.row < 11
        and node.id not in {
            "military_army_defense_i",
            "military_army_health_i",
        }
    }


def test_monster_hunt_visible_connections_use_level_one_unlocks_only() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    monster_hunt = next(
        item for item in categories if item.category_id == "monster_hunt"
    )
    groups = {
        (group.prerequisite_ids, group.research_ids)
        for group in monster_hunt.connection_groups
    }

    upper_ids = (
        "monster_hunt_energy_recovery_i",
        "monster_hunt_energy_limit_i",
        "monster_hunt_energy_saver_i",
    )
    monster_hunt_two = ("monster_hunt_monster_hunt_ii",)
    lower_ids = (
        "monster_hunt_aggressive_hunter_i",
        "monster_hunt_animal_handling",
        "monster_hunt_monster_hunter_i",
    )
    assert (upper_ids, monster_hunt_two) in groups
    assert (monster_hunt_two, lower_ids) in groups

    visible_pairs = {
        (prerequisite_id, research_id)
        for prerequisites, research in groups
        for prerequisite_id in prerequisites
        for research_id in research
    }
    assert (
        "monster_hunt_energy_recovery_i",
        "monster_hunt_aggressive_hunter_i",
    ) not in visible_pairs
    assert (
        "monster_hunt_energy_limit_i",
        "monster_hunt_animal_handling",
    ) not in visible_pairs
    assert (
        "monster_hunt_energy_saver_i",
        "monster_hunt_monster_hunter_i",
    ) not in visible_pairs

    assert (
        "monster_hunt_animal_handling",
        "monster_hunt_monster_hunt_iii",
    ) in visible_pairs
    assert any(
        group.prerequisite_ids == ("monster_hunt_animal_handling",)
        and group.research_ids == ("monster_hunt_monster_hunt_iii",)
        for group in monster_hunt.connection_groups
    )

    aggressive_hunter = monster_hunt.node_by_id()[
        "monster_hunt_aggressive_hunter_i"
    ].level_data(1)
    assert aggressive_hunter is not None
    assert {
        (requirement.research_id, requirement.level)
        for requirement in aggressive_hunter.requirements
    } == {("monster_hunt_monster_hunt_ii", 1)}


def test_defense_uses_the_screen_shaped_trap_connection_buses() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    defense = next(item for item in categories if item.category_id == "defense")
    assert len(defense.connection_groups) == 9
    same_row_group = next(
        group
        for group in defense.connection_groups
        if group.prerequisite_ids == ("defense_trap_power_i",)
        and len(group.research_ids) == 2
    )
    assert set(same_row_group.research_ids) == {
        "defense_trap_defense_i",
        "defense_trap_durability_i",
    }
    assert any(
        group.prerequisite_ids == ("defense_trap_power_i",)
        and group.research_ids == ("defense_wall_strength_i",)
        for group in defense.connection_groups
    )


def test_upgrade_defenses_keeps_vertical_and_same_row_unlocks_separate() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    category = next(
        item for item in categories if item.category_id == "upgrade_defenses"
    )
    groups = {
        (group.prerequisite_ids, group.research_ids)
        for group in category.connection_groups
    }

    assert groups == {
        (
            ("upgrade_defenses_trap_retrieval_i",),
            ("upgrade_defenses_wall_repair_i",),
        ),
        (
            ("upgrade_defenses_wall_repair_i",),
            (
                "upgrade_defenses_wall_defense_i",
                "upgrade_defenses_wall_durability_i",
            ),
        ),
        (
            (
                "upgrade_defenses_wall_defense_i",
                "upgrade_defenses_wall_repair_i",
                "upgrade_defenses_wall_durability_i",
            ),
            ("upgrade_defenses_trap_retrieval_ii",),
        ),
        (
            ("upgrade_defenses_trap_retrieval_ii",),
            ("upgrade_defenses_trap_strength_ii",),
        ),
        (
            ("upgrade_defenses_trap_strength_ii",),
            (
                "upgrade_defenses_trap_defense_ii",
                "upgrade_defenses_trap_durability_ii",
            ),
        ),
        (
            (
                "upgrade_defenses_trap_defense_ii",
                "upgrade_defenses_trap_strength_ii",
                "upgrade_defenses_trap_durability_ii",
            ),
            ("upgrade_defenses_trap_retrieval_iii",),
        ),
        (
            ("upgrade_defenses_trap_retrieval_iii",),
            (
                "upgrade_defenses_wall_defense_ii",
                "upgrade_defenses_wall_repair_ii",
                "upgrade_defenses_wall_durability_ii",
            ),
        ),
        (
            ("upgrade_defenses_wall_repair_ii",),
            ("upgrade_defenses_trap_crafting_ii",),
        ),
        (
            (
                "upgrade_defenses_wall_defense_ii",
                "upgrade_defenses_trap_crafting_ii",
                "upgrade_defenses_wall_durability_ii",
            ),
            ("upgrade_defenses_trap_retrieval_iv",),
        ),
    }


def test_every_catalog_node_has_a_sourced_maximum_and_declares_missing_effects() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    assert all(category.nodes for category in categories)
    assert all(category.edges for category in categories)
    assert all(node.max_level is not None for category in categories for node in category.nodes)
    missing_effects = {
        node.id
        for category in categories
        for node in category.nodes
        if any(
            not node.effect_at(level)
            for level in range(1, int(node.max_level or 0) + 1)
        )
    }
    assert missing_effects == {"military_intelligence_report"}
    assert all("ja-JP" in node.names for category in categories for node in category.nodes)
    assert all(
        node.localized_name("ja-JP") != "XXX"
        for category in categories
        for node in category.nodes
    )


def test_catalog_loads_level_cost_time_and_exact_prerequisite_levels() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    economy = next(item for item in categories if item.category_id == "economy")
    construction = economy.node_by_id()["economy_construction_speed"]
    level_one = construction.level_data(1)
    assert level_one is not None
    assert level_one.academy_level == 1
    assert level_one.base_time_seconds == 420
    assert level_one.power == 180
    assert level_one.costs == {
        "food": 571,
        "stone": 714,
        "timber": 1_142,
        "ore": 429,
        "gold": 794,
    }
    assert level_one.costs_verified

    defense = next(item for item in categories if item.category_id == "defense")
    durability = defense.node_by_id()["defense_trap_durability_i"]
    level_eight = durability.level_data(8)
    assert level_eight is not None
    assert [(item.research_id, item.level) for item in level_eight.requirements] == [
        ("defense_trap_power_i", 7)
    ]


def test_lunar_foundry_is_the_one_level_unlock_research() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    gear = next(item for item in categories if item.category_id == "gear")
    foundry = next(
        node
        for node in gear.nodes
        if node.localized_name("en-US") == "Lunar Foundry"
    )

    assert foundry.max_level == 1
    assert foundry.effect_label == "Unlock"
    assert foundry.effect_at(1) == "Unlocks Lunar Foundry"
    level_one = foundry.level_data(1)
    assert level_one is not None
    assert level_one.academy_level == 25
    assert level_one.base_time_seconds == 13 * 86_400 + 5 * 3_600
    assert level_one.technolabe_count == 1
    assert level_one.power == 94_383
    assert level_one.costs == {
        "food": 488_059,
        "stone": 366_044,
        "timber": 305_037,
        "ore": 305_037,
        "gold": 572_165,
        "ancient_tomes": 30,
    }
    assert {
        (requirement.research_id, requirement.level)
        for requirement in level_one.requirements
    } == {
        ("gear_bigger_infirmary_iii", 4),
        ("gear_barracks_expansion_ii", 4),
    }

    plan = CatalogResearchPlanner(categories).create_plan(
        PlayerState(
            research_levels={
                "gear_bigger_infirmary_iii": 4,
                "gear_barracks_expansion_ii": 4,
            }
        ),
        foundry.id,
        1,
    )
    assert [(step.research_id, step.base_time_seconds) for step in plan.steps] == [
        (foundry.id, 13 * 86_400 + 5 * 3_600)
    ]
    assert plan.unknown_time_steps == 0


def test_every_catalog_tree_has_unique_positions_and_valid_acyclic_edges() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    for category in categories:
        node_ids = {node.id for node in category.nodes}
        assert len(node_ids) == len(category.nodes)
        positions = {(node.row, node.column) for node in category.nodes}
        assert len(positions) == len(category.nodes)
        assert all(row >= 0 and column >= 0 for row, column in positions)

        edge_pairs = {
            (edge.prerequisite_id, edge.research_id) for edge in category.edges
        }
        assert len(edge_pairs) == len(category.edges)
        assert all(
            prerequisite in node_ids
            and research in node_ids
            and prerequisite != research
            for prerequisite, research in edge_pairs
        )

        remaining = set(node_ids)
        resolved: set[str] = set()
        while remaining:
            ready = {
                research_id
                for research_id in remaining
                if all(
                    prerequisite in resolved
                    for prerequisite, research in edge_pairs
                    if research == research_id
                )
            }
            assert ready, f"cycle in {category.category_id}"
            resolved.update(ready)
            remaining.difference_update(ready)


def test_every_catalog_level_prerequisite_graph_is_acyclic() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    for category in categories:
        planner = CatalogResearchPlanner((category,))
        required = {
            node.id: node.max_level
            for node in category.nodes
            if node.max_level is not None
        }
        planner._topological_step_order(required, {})


def test_monster_hunt_iv_plan_does_not_reenter_hunter_recovery_level_eight() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    planner = CatalogResearchPlanner(categories)

    result = planner.create_plan(
        PlayerState(), "monster_hunt_monster_hunt_iv", 1
    )

    assert result.required_levels["monster_hunt_hunter_recovery_ii"] == 8
    assert "monster_hunt_monster_hunter_iii" not in result.required_levels


def test_every_visible_connection_has_valid_rows_and_both_ends() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    for category in categories:
        nodes = category.node_by_id()
        incoming_counts = {node.id: 0 for node in category.nodes}
        for group in category.connection_groups:
            assert group.prerequisite_ids
            assert group.research_ids
            assert all(
                research_id in nodes
                for research_id in (
                    *group.prerequisite_ids,
                    *group.research_ids,
                )
            )
            prerequisite_rows = {
                nodes[research_id].row
                for research_id in group.prerequisite_ids
            }
            research_rows = {
                nodes[research_id].row for research_id in group.research_ids
            }
            assert len(research_rows) == 1, category.category_id
            research_row = next(iter(research_rows))
            assert all(
                prerequisite_row <= research_row
                for prerequisite_row in prerequisite_rows
            ), category.category_id
            occupied_positions = {
                (node.row, node.column) for node in category.nodes
            }
            for prerequisite_id in group.prerequisite_ids:
                prerequisite = nodes[prerequisite_id]
                if research_row - prerequisite.row > 1:
                    assert all(
                        (row, prerequisite.column) not in occupied_positions
                        for row in range(prerequisite.row + 1, research_row)
                    ), category.category_id
            for research_id in group.research_ids:
                incoming_counts[research_id] += 1

        assert all(
            incoming_counts[node.id] >= 1
            for node in category.nodes
            if node.row > 0
        ), category.category_id


def test_every_visible_connection_pair_has_catalog_or_level_one_evidence() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    for category in categories:
        nodes = category.node_by_id()
        grounded_pairs = {
            (edge.prerequisite_id, edge.research_id)
            for edge in category.edges
        }
        for research in category.nodes:
            level_one = research.level_data(1)
            if level_one is None:
                continue
            grounded_pairs.update(
                (requirement.research_id, research.id)
                for requirement in level_one.requirements
                if requirement.research_id in nodes
            )

        visible_pairs = {
            (prerequisite_id, research_id)
            for group in category.connection_groups
            for prerequisite_id in group.prerequisite_ids
            for research_id in group.research_ids
        }
        assert visible_pairs <= grounded_pairs, category.category_id


def test_unobstructed_level_one_skip_connections_are_visible() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    checked_pairs: set[tuple[str, str]] = set()
    for category in categories:
        nodes = category.node_by_id()
        occupied_positions = {
            (node.row, node.column) for node in category.nodes
        }
        visible_pairs = {
            (prerequisite_id, research_id)
            for group in category.connection_groups
            for prerequisite_id in group.prerequisite_ids
            for research_id in group.research_ids
        }
        for research in category.nodes:
            level_one = research.level_data(1)
            if level_one is None:
                continue
            for requirement in level_one.requirements:
                prerequisite = nodes.get(requirement.research_id)
                if (
                    prerequisite is None
                    or research.row - prerequisite.row <= 1
                    or any(
                        (row, prerequisite.column) in occupied_positions
                        for row in range(
                            prerequisite.row + 1, research.row
                        )
                    )
                ):
                    continue
                pair = (prerequisite.id, research.id)
                checked_pairs.add(pair)
                assert pair in visible_pairs, category.category_id

    assert checked_pairs == {
        (
            "monster_hunt_animal_handling",
            "monster_hunt_monster_hunt_iii",
        ),
        (
            "familiar_battles_familiarity_infantry_def_i",
            "familiar_battles_familiarity_infantry_def_ii",
        ),
        (
            "familiar_battles_familiarity_cavalry_def_i",
            "familiar_battles_familiarity_cavalry_def_ii",
        ),
        (
            "upgrade_defenses_wall_defense_ii",
            "upgrade_defenses_trap_retrieval_iv",
        ),
        (
            "upgrade_defenses_wall_durability_ii",
            "upgrade_defenses_trap_retrieval_iv",
        ),
    }


def test_wonder_infantry_second_tier_uses_forward_visual_dependency() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    wonder = next(
        item for item in categories if item.category_id == "wonder_battles"
    )
    visible_pairs = {
        (prerequisite_id, research_id)
        for group in wonder.connection_groups
        for prerequisite_id in group.prerequisite_ids
        for research_id in group.research_ids
    }
    assert (
        "wonder_battles_infantry_defense_wonder_ii",
        "wonder_battles_infantry_durability_wonder_ii",
    ) in visible_pairs
    assert (
        "wonder_battles_infantry_offense_wonder_ii",
        "wonder_battles_infantry_durability_wonder_ii",
    ) not in visible_pairs


def test_guild_duel_public_tree_keeps_structure_without_claiming_numeric_data() -> None:
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()
    guild_duel = next(item for item in categories if item.category_id == "guild_duel")
    assert len(guild_duel.nodes) == 26
    assert len(guild_duel.edges) == 44
    assert (
        guild_duel.verification_status
        == "structure_only_numeric_level_data_unavailable"
    )
    gathering = guild_duel.node_by_id()["guild_duel_gathering_incentive"]
    reward = guild_duel.node_by_id()["guild_duel_reward_incentive_i"]
    assert gathering.localized_name("ja-JP") == "採取インセンティブ"
    assert gathering.max_level == 10
    assert gathering.effect_at(10) == "+50%"
    assert reward.max_level == 1
    assert reward.effect_at(1) == "Unlocked"
    army_attack = guild_duel.node_by_id()["guild_duel_army_atk_iii"]
    assert army_attack.effect_label == "Army ATK"
