"""
Unit tests for Renee Item Button Inventory Fix and Full-Fledged PvP Combat Mode.
"""

import asyncio
import time
import unittest
from unittest.mock import MagicMock, AsyncMock

import yuna_renee
import yuna_pvp
import yuna_gambling


class MockUser:
    def __init__(self, uid: int, name: str = "Player", bot: bool = False):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f"<@{uid}>"
        self.bot = bot


class MockGuild:
    def __init__(self, members=None):
        self.members = members or []

    def get_member(self, uid: int):
        for m in self.members:
            if m.id == uid:
                return m
        return None


class MockMessage:
    def __init__(self, author=None, content="", channel=None, mentions=None, guild=None):
        self.id = 99999
        self.author = author or MockUser(1001, "Alice")
        self.content = content
        self.channel = channel
        self.mentions = mentions or []
        self.guild = guild
        self.replies = []

    async def reply(self, content=None, embed=None, view=None, **kwargs):
        self.replies.append({"content": content, "embed": embed, "view": view})
        return self

    async def edit(self, content=None, embed=None, view=None):
        if content is not None:
            self.content = content
        if embed is not None:
            self.embed = embed
        if view is not None:
            self.view = view


class MockInteractionResponse:
    def __init__(self):
        self._done = False
        self.sent_messages = []

    def is_done(self):
        return self._done

    async def defer(self, ephemeral=False):
        self._done = True

    async def send_message(self, content=None, embed=None, view=None, ephemeral=False):
        self._done = True
        self.sent_messages.append({"content": content, "embed": embed, "view": view, "ephemeral": ephemeral})

    async def edit_message(self, content=None, embed=None, view=None):
        self._done = True
        self.sent_messages.append({"content": content, "embed": embed, "view": view})


class MockChannel:
    def __init__(self, cid=55555):
        self.id = cid
        self.sent_messages = []

    async def send(self, content=None, embed=None, view=None):
        msg = MockMessage(author=None, content=content, channel=self)
        msg.embed = embed
        msg.view = view
        self.sent_messages.append(msg)
        return msg


class MockInteraction:
    def __init__(self, user_id: int, custom_id: str = "", values=None, client=None, channel=None, message=None):
        self.user = MockUser(user_id)
        self.response = MockInteractionResponse()
        self.data = {"custom_id": custom_id, "values": values or []}
        self.client = client
        self.channel = channel if channel is not None else MockChannel()
        self.message = message if message is not None else MockMessage()


class TestReneeItemButtonFix(unittest.TestCase):
    def test_get_player_consumable_inventory(self):
        stats = {
            "watermelons": 25,
            "inventory": {
                "healing_potion": 3,
                "potion": 2,
                "dungeon_elixir": 1,
                "katana": 1, # Equipment, should be excluded
                "smoke_bomb": 4
            }
        }
        consumables = yuna_renee.get_player_consumable_inventory(stats)
        self.assertIn("watermelons", consumables)
        self.assertEqual(consumables["watermelons"], 25)
        self.assertIn("healing_potion", consumables)
        self.assertIn("dungeon_elixir", consumables)
        self.assertIn("smoke_bomb", consumables)
        self.assertNotIn("katana", consumables)

    def test_on_item_opens_menu_not_attack(self):
        """Verify on_item displays the consumable inventory menu without executing an attack."""
        user = MockUser(12345, "Hero")
        chan = MagicMock()
        controller = yuna_renee.ReneeBattleController(chan, user, None)
        controller.p_stats["inventory"] = {"healing_potion": 2, "dungeon_elixir": 1}
        view = yuna_renee.ReneeBattleView(controller)

        inter = MockInteraction(12345, "renee_duel_item")
        asyncio.run(view.on_item(inter))

        self.assertTrue(inter.response.is_done())
        self.assertTrue(controller.action_queue.empty()) # Crucial: Must NOT queue an attack!
        sent = inter.response.sent_messages[0]
        self.assertIsNotNone(sent.get("embed"))
        self.assertIn("INVENTORY", sent["embed"].title)
        self.assertIsInstance(sent.get("view"), yuna_renee.ReneeItemSelectView)

    def test_renee_item_action_uses_consumable(self):
        """Verify executing item action heals player and deducts from inventory."""
        user = MockUser(12345, "Hero")
        chan = MagicMock()
        controller = yuna_renee.ReneeBattleController(chan, user, None)
        controller.player_hp = 500
        controller.player_max_hp = 2000
        controller.p_stats["inventory"] = {"healing_potion": 3}

        # Put item action into queue
        inter = MockInteraction(12345, "renee_duel_item_select", values=["healing_potion"])
        item_view = yuna_renee.ReneeItemSelectView(controller, controller.p_stats["inventory"])
        asyncio.run(item_view.on_select(inter))

        queued = asyncio.run(controller.action_queue.get())
        self.assertEqual(queued["type"], "item")
        self.assertEqual(queued["item_id"], "healing_potion")


class TestPvPBattleMode(unittest.TestCase):
    def setUp(self):
        yuna_gambling._PENDING_CHALLENGES.clear()
        self.p1 = MockUser(1001, "Alice")
        self.p2 = MockUser(1002, "Bob")
        self.chan = MagicMock()
        self.chan.id = 55555

        yuna_gambling._USER_STATS["1001"] = {
            "berries": 5000,
            "inventory": {"healing_potion": 3, "smoke_bomb": 1},
            "unlocked_skills": ["power_strike", "shield_bash", "mana_surge"]
        }
        yuna_gambling._USER_STATS["1002"] = {
            "berries": 5000,
            "inventory": {"dungeon_elixir": 2},
            "unlocked_skills": ["power_strike", "mending_light"]
        }

    def test_pvp_view_only_has_skill_item_flee_buttons(self):
        """Verify PvP battle view contains skill dropdown, [Items], and [Quit], and direct skill buttons are removed."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=100,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        view = controller.view
        buttons = [item for item in view.children if isinstance(item, yuna_pvp.Button)]
        selects = [item for item in view.children if isinstance(item, yuna_pvp.Select)]

        btn_labels = [b.label for b in buttons]
        self.assertTrue(any("Skills" in lbl or "✨" in lbl for lbl in btn_labels))
        self.assertTrue(any("Items" in lbl or "🎒" in lbl for lbl in btn_labels))
        self.assertTrue(any("Quit" in lbl or "🏳️" in lbl for lbl in btn_labels))
        # Direct skill buttons are removed from public view
        self.assertFalse(any(btn.custom_id.startswith("pvp_btn_sk_") for btn in buttons))

        # Skill selection is in private ephemeral view per player
        p1_skill_view = yuna_pvp.PvPSkillSelectView(controller, "1001")
        p1_selects = [item for item in p1_skill_view.children if isinstance(item, yuna_pvp.Select)]
        self.assertTrue(any(s.custom_id.startswith("pvp_ephemeral_select_skill_") for s in p1_selects))

    def test_pvp_direct_skill_selection_flow(self):
        """Verify selecting a skill from the dropdown locks in the skill."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=100,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )

        # Select first available skill from dropdown via ephemeral skill view
        p1_skill_view = yuna_pvp.PvPSkillSelectView(controller, "1001")
        p1_select = [item for item in p1_skill_view.children if isinstance(item, yuna_pvp.Select)][0]
        chosen_skill_id = p1_select.options[0].value
        inter = MockInteraction(1001, "pvp_ephemeral_select_skill_1001", values=[chosen_skill_id])
        asyncio.run(p1_skill_view.on_select(inter))

        self.assertTrue(inter.response.is_done())
        self.assertIn("1001", controller.locked_actions)
        self.assertEqual(controller.locked_actions["1001"]["skill_id"], chosen_skill_id)

    def test_pvp_direct_item_selection_flow(self):
        """Verify selecting an item locks it in."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=100,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        view = controller.view

        inter = MockInteraction(1001, "pvp_select_item", values=["healing_potion"])
        asyncio.run(view.on_item_select(inter))

        self.assertTrue(inter.response.is_done())
        self.assertIn("1001", controller.locked_actions)
        self.assertEqual(controller.locked_actions["1001"]["item_id"], "healing_potion")

    def test_pvp_third_party_player_blocked(self):
        """Verify non-participating player cannot interact with the duel."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=100,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        view = controller.view

        inter_stranger = MockInteraction(9999, "pvp_select_skill", values=["power_strike"])
        asyncio.run(yuna_pvp.handle_pvp_interaction(inter_stranger))

        self.assertTrue(inter_stranger.response.is_done())
        sent = inter_stranger.response.sent_messages[0]
        self.assertIn("not your duel", sent["content"].lower())
        self.assertNotIn("9999", controller.locked_actions)

    def test_pvp_flee_forfeits_match(self):
        """Verify clicking flee forfeits duel and awards victory to opponent."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=100,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        controller.active_id = "1001"
        res = asyncio.run(controller.execute_action({"type": "flee"}))
        self.assertIn("fled from the duel", res)
        self.assertEqual(controller.p1_hp, 0)
        self.assertTrue(controller.ended)

    def test_pvp_end_to_end_combat_and_pot_payout(self):
        """Verify full PvP match finishes with winner pot payout and stats update."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=200,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        # Give P1 lethal strike against low HP P2
        controller.p2_hp = 50
        controller.active_id = "1001"
        res = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "power_strike"}))
        self.assertIn("Power Strike", res)
        self.assertLessEqual(controller.p2_hp, 0)

        # Finish duel
        initial_p1_berries = yuna_gambling._USER_STATS["1001"].get("berries", 0)
        asyncio.run(controller.finish_duel(winner_id="1001", loser_id="1002"))
        self.assertTrue(controller.ended)
        # Winner should have pot (400 berries) added
        self.assertGreaterEqual(yuna_gambling._USER_STATS["1001"].get("berries", 0), initial_p1_berries + 400)
        self.assertGreaterEqual(yuna_gambling._USER_STATS["1001"].get("fights_won", 0), 1)
        # All buttons in view disabled
        self.assertTrue(all(btn.disabled for btn in controller.view.children))

    def test_spousal_friendlyduel_auto_targets_spouse(self):
        """Verify y!friendlyduel with no mention automatically targets spouse with 0 berries wager."""
        yuna_gambling._USER_STATS["1001"]["spouse"] = "1002"
        yuna_gambling._USER_STATS["1002"]["spouse"] = "1001"
        guild = MockGuild([self.p1, self.p2])
        msg = MockMessage(author=self.p1, content="y!friendlyduel", guild=guild)

        asyncio.run(yuna_gambling.handle_friendlyduel(msg, client=None, args=[]))

        c_id = "friendlyduel_1002"
        self.assertIn(c_id, yuna_gambling._PENDING_CHALLENGES)
        c_data = yuna_gambling._PENDING_CHALLENGES[c_id]
        self.assertEqual(c_data["amount"], 0)
        self.assertEqual(c_data["target_id"], "1002")
        self.assertTrue(len(msg.replies) > 0)
        reply_txt = msg.replies[0]["content"]
        self.assertIn("Spousal Friendly Duel Challenge", reply_txt)
        self.assertIn("beloved spouse", reply_txt)

    def test_spousal_wager_fight_blocked_with_friendlyduel_hint(self):
        """Verify real wager fight against spouse is blocked and directs to friendlyduel."""
        yuna_gambling._USER_STATS["1001"]["spouse"] = "1002"
        yuna_gambling._USER_STATS["1002"]["spouse"] = "1001"
        guild = MockGuild([self.p1, self.p2])
        msg = MockMessage(author=self.p1, content="y!fight @Bob 500", mentions=[self.p2], guild=guild)

        asyncio.run(yuna_gambling.handle_fight(msg, client=None, args=["<@1002>", "500"]))

        self.assertNotIn("fight_1002", yuna_gambling._PENDING_CHALLENGES)
        self.assertTrue(len(msg.replies) > 0)
        reply_txt = msg.replies[0]["content"]
        self.assertIn("Domestic disputes with money on the line aren't allowed", reply_txt)
        self.assertIn("y!friendlyduel", reply_txt)

    def test_spousal_pvp_battle_theme_and_resolution(self):
        """Verify married couple PvP uses Spousal Duel theme and friendly victory."""
        yuna_gambling._USER_STATS["1001"]["spouse"] = "1002"
        yuna_gambling._USER_STATS["1002"]["spouse"] = "1001"
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=0,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        self.assertTrue(controller.is_couple)

        # Render initial embed
        embed = controller.render_embed("Round 1 start!")
        self.assertIn("SPOUSAL DUEL", embed.title)
        self.assertEqual(embed.color.value, 0xFF69B4)
        self.assertIn("Spousal Sparring", embed.footer.text)

        # Finish duel
        msg = MockMessage()
        controller.battle_message = msg
        mock_update = AsyncMock()
        with unittest.mock.patch.object(yuna_gambling, "_update_user_stats", mock_update):
            asyncio.run(controller.finish_duel(winner_id="1001", loser_id="1002"))
        self.assertTrue(controller.ended)
        # In a friendly 0-pot spousal duel, _update_user_stats should never be called to deduct or add berries
        mock_update.assert_not_called()
        self.assertIsNotNone(msg.embed)
        self.assertIn("SPOUSAL DUEL VICTOR", msg.embed.title)
        self.assertIn("beloved spouse", msg.embed.description)

    def test_dispatch_friendlyduel_command(self):
        """Verify _dispatch_yuna_command handles 'friendlyduel' and 'spar' aliases."""
        yuna_gambling._USER_STATS["1001"]["spouse"] = "1002"
        guild = MockGuild([self.p1, self.p2])
        msg = MockMessage(author=self.p1, content="y!spar", guild=guild)

        dispatched = asyncio.run(yuna_gambling._dispatch_yuna_command(msg, client=None, cmd="spar", args=[], author_id="1001"))
        self.assertTrue(dispatched)
        self.assertIn("friendlyduel_1002", yuna_gambling._PENDING_CHALLENGES)

    def test_accept_btn_click_pvp_starts_without_nameerror(self):
        """Verify clicking Accept button on challenge resolves and launches battle without NameError."""
        c_data = {
            "author_id": "1001",
            "author_mention": "<@1001>",
            "target_id": "1002",
            "target_mention": "<@1002>",
            "amount": 0,
            "challenge_type": "friendlyduel",
            "custom_text": None,
            "message": MockMessage(),
            "client": None,
            "channel": self.chan
        }
        yuna_gambling._PENDING_CHALLENGES["friendlyduel_1002"] = c_data
        view = yuna_gambling.ChallengeView("1002", "1001", "friendlyduel", c_data)
        inter = MockInteraction(1002, "challenge_accept")

        mock_start_pvp = AsyncMock()
        with unittest.mock.patch("yuna_pvp.start_pvp_battle", mock_start_pvp):
            asyncio.run(view.accept_btn.callback(inter))

        self.assertNotIn("friendlyduel_1002", yuna_gambling._PENDING_CHALLENGES)
        mock_start_pvp.assert_called_once()
        call_kwargs = mock_start_pvp.call_args[1]
        self.assertEqual(call_kwargs["data"]["challenge_type"], "friendlyduel")
        self.assertEqual(call_kwargs["interaction"], inter)

    def test_handle_accept_text_command_starts_pvp(self):
        """Verify text command y!accept resolves pending challenge and launches PvP battle."""
        c_data = {
            "author_id": "1001",
            "author_mention": "<@1001>",
            "target_id": "1002",
            "target_mention": "<@1002>",
            "amount": 100,
            "challenge_type": "fight",
            "custom_text": None,
            "message": MockMessage(),
            "client": None,
            "channel": self.chan
        }
        yuna_gambling._PENDING_CHALLENGES["fight_1002"] = c_data
        msg = MockMessage(author=self.p2, content="y!accept")

        mock_start_pvp = AsyncMock()
        with unittest.mock.patch("yuna_pvp.start_pvp_battle", mock_start_pvp):
            asyncio.run(yuna_gambling.handle_accept(msg, client=None, args=[]))

        self.assertNotIn("fight_1002", yuna_gambling._PENDING_CHALLENGES)
        mock_start_pvp.assert_called_once()


class TestNewPvPDuelSystem(unittest.TestCase):
    def setUp(self):
        yuna_pvp.ACTIVE_PVP_BATTLES.clear()
        yuna_pvp.PENDING_DUEL_REQUESTS.clear()
        self.p1 = MockUser(2001, "Kirito")
        self.p2 = MockUser(2002, "Asuna")
        self.bot_user = MockUser(9999, "Robot", bot=True)
        self.chan = MagicMock()
        self.chan.id = 77777

        yuna_gambling._USER_STATS["2001"] = {
            "battle_level": 50,
            "rpg_class": "dps",
            "inventory": {"healing_potion": 2, "phoenix_feather": 1, "smoke_bomb": 1},
            "equipped_skills": ["brawler_strike", "wild_haymaker", "cleave_edge", "war_cry"],
            "training_atk": 20,
            "training_spd": 25
        }
        yuna_gambling._USER_STATS["2002"] = {
            "battle_level": 50,
            "rpg_class": "healer",
            "inventory": {"dungeon_elixir": 1},
            "equipped_skills": ["mending_light", "mana_surge"],
            "training_atk": 10,
            "training_spd": 15
        }

    def test_duel_command_request_creation_and_view(self):
        """Verify y!duel @user creates a 2-minute duel request with [Accept] and [Decline]."""
        guild = MockGuild([self.p1, self.p2])
        msg = MockMessage(author=self.p1, content="y!duel @Asuna", mentions=[self.p2], guild=guild)

        asyncio.run(yuna_pvp.handle_duel(msg, client=None, args=["<@2002>"]))

        self.assertEqual(len(msg.replies), 1)
        reply = msg.replies[0]
        self.assertIn("DUEL REQUEST", reply["embed"].title)
        self.assertIn("Kirito", reply["embed"].description)
        self.assertIsInstance(reply["view"], yuna_pvp.DuelRequestView)

        # Check pending request tracking
        req = yuna_pvp.get_pending_duel_for_target("2002", "2001")
        self.assertIsNotNone(req)
        self.assertEqual(req["status"], "PENDING")
        self.assertGreater(req["expires_at"], time.time())

    def test_duel_request_expiration_after_2min(self):
        """Verify duel request expires after 120 seconds and disables buttons."""
        req_id = "test_req_expire"
        req_data = {
            "id": req_id,
            "author_id": "2001",
            "author_name": "Kirito",
            "target_id": "2002",
            "target_name": "Asuna",
            "status": "PENDING",
            "created_at": time.time() - 130, # 130s ago
            "expires_at": time.time() - 10,
            "message": MockMessage()
        }
        yuna_pvp.PENDING_DUEL_REQUESTS[req_id] = req_data
        view = yuna_pvp.DuelRequestView(req_id, req_data)

        asyncio.run(view.on_timeout())
        self.assertEqual(req_data["status"], "EXPIRED")
        self.assertTrue(all(btn.disabled for btn in view.children))

        # Attempt to accept expired request should be blocked
        inter = MockInteraction(2002, f"duel_accept_{req_id}")
        asyncio.run(view.on_accept(inter))
        self.assertEqual(req_data["status"], "EXPIRED")

    def test_duel_safety_self_and_bot_blocked(self):
        """Verify challenging oneself or a bot is rejected immediately."""
        guild = MockGuild([self.p1, self.bot_user])

        # Self duel
        msg_self = MockMessage(author=self.p1, content="y!duel @Kirito", mentions=[self.p1], guild=guild)
        asyncio.run(yuna_pvp.handle_duel(msg_self, client=None, args=["<@2001>"]))
        self.assertIn("can't duel yourself", msg_self.replies[0]["content"])

        # Bot duel
        msg_bot = MockMessage(author=self.p1, content="y!duel @Robot", mentions=[self.bot_user], guild=guild)
        asyncio.run(yuna_pvp.handle_duel(msg_bot, client=None, args=["<@9999>"]))
        self.assertIn("Bots do not engage", msg_bot.replies[0]["content"])

    def test_duel_safety_duplicate_outgoing_request_blocked(self):
        """Verify player cannot send multiple active duel requests simultaneously."""
        guild = MockGuild([self.p1, self.p2])
        msg1 = MockMessage(author=self.p1, content="y!duel @Asuna", mentions=[self.p2], guild=guild)
        asyncio.run(yuna_pvp.handle_duel(msg1, client=None, args=["<@2002>"]))

        # Second request from same author while first is pending
        msg2 = MockMessage(author=self.p1, content="y!duel @Asuna", mentions=[self.p2], guild=guild)
        asyncio.run(yuna_pvp.handle_duel(msg2, client=None, args=["<@2002>"]))
        self.assertIn("already have a pending duel request", msg2.replies[0]["content"])

    def test_duel_level_selection_and_scaling(self):
        """Verify level selection scales stats to specified duel level up to 3000."""
        # Level 2000 duel
        controller_lvl2000 = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=0,
            client=None,
            yuna_gambling_mod=yuna_gambling,
            duel_level=2000
        )
        self.assertEqual(controller_lvl2000.duel_level, 2000)
        # Stats should be scaled up to lv2000 values
        self.assertGreater(controller_lvl2000.p1_max_hp, 50000)
        self.assertGreater(controller_lvl2000.p1_rpg["atk"], 10000)

        # Level > 3000 should be clamped to 3000
        controller_lvl4000 = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            wager_amount=0,
            client=None,
            yuna_gambling_mod=yuna_gambling,
            duel_level=4000
        )
        self.assertEqual(controller_lvl4000.duel_level, 3000)

    def test_speed_first_turn_determination(self):
        """Verify higher SPD gets first turn, with tiebreaker if equal."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        p1_spd = controller.p1_rpg["spd"]
        p2_spd = controller.p2_rpg["spd"]

        if p1_spd > p2_spd:
            self.assertEqual(controller.active_id, "2001")
        elif p2_spd > p1_spd:
            self.assertEqual(controller.active_id, "2002")
        else:
            self.assertIn(controller.active_id, ("2001", "2002"))

    def test_speed_difference_dodge_system(self):
        """Verify dodge chance scales based on difference in actual SPD values."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        # Substantial difference: 5,000 SPD vs 1,000 SPD
        controller.p1_rpg["spd"] = 1000
        controller.p2_rpg["spd"] = 5000
        controller.p2_rpg["dodge_bonus"] = 0.0

        # Simulate 1000 attack checks: defender p2 (5000) vs attacker p1 (1000)
        dodges_big = sum(1 for _ in range(1000) if controller.check_dodge("2001", "2002")[0])
        dodge_rate_big = dodges_big / 1000.0
        # Expected dodge: (4000 / 6000) * 0.35 ≈ 0.233 (23%)
        self.assertGreater(dodge_rate_big, 0.15)
        self.assertLessEqual(dodge_rate_big, 0.35) # Capped at 35%

        # Negligible difference: 5,000 SPD vs 4,900 SPD
        controller.p1_rpg["spd"] = 4900
        controller.p2_rpg["spd"] = 5000
        dodges_small = sum(1 for _ in range(1000) if controller.check_dodge("2001", "2002")[0])
        dodge_rate_small = dodges_small / 1000.0
        # Expected dodge: (100 / 9900) * 0.35 ≈ 0.0035 (< 1%)
        self.assertLess(dodge_rate_small, 0.05)

    def test_simultaneous_skill_lock_in_selection(self):
        """Verify selecting a skill locks it in for that player."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        view = controller.view

        # Select primary skill
        inter = MockInteraction(2001, "pvp_select_skill", values=["brawler_strike"])
        asyncio.run(yuna_pvp.handle_pvp_interaction(inter))

        self.assertIn("2001", controller.locked_actions)
        self.assertEqual(controller.locked_actions["2001"]["type"], "skill")
        self.assertEqual(controller.locked_actions["2001"]["skill_id"], "brawler_strike")

    def test_usable_inventory_items_view_and_consumption(self):
        """Verify [Items] displays usable items and consuming one deducts from inventory."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        controller.active_id = "2001"
        view = controller.view

        # Switch to items mode
        inter_open = MockInteraction(2001, "pvp_btn_open_items")
        asyncio.run(view.on_open_items(inter_open))

        # Use healing potion
        init_potions = yuna_gambling._USER_STATS["2001"]["inventory"]["healing_potion"]
        controller.p1_hp = 500
        res = asyncio.run(controller.execute_action({"type": "item", "item_id": "healing_potion"}, actor_id="2001"))

        self.assertIn("Healing Potion", res)
        self.assertGreater(controller.p1_hp, 500)
        # Inventory deducted
        self.assertEqual(yuna_gambling._USER_STATS["2001"]["inventory"]["healing_potion"], init_potions - 1)

    def test_quit_button_confirmation_and_forfeit(self):
        """Verify tapping Quit asks for confirmation; Yes forfeits match and No returns."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        view = controller.view

        # Tap Quit
        inter_quit = MockInteraction(2001, "pvp_btn_open_quit")
        asyncio.run(view.on_open_quit(inter_quit))

        # Cancel quit view
        quit_view = yuna_pvp.PvPQuitConfirmView(controller, "2001")
        inter_cancel = MockInteraction(2001, "pvp_btn_cancel_quit")
        asyncio.run(quit_view.on_cancel(inter_cancel))
        self.assertFalse(controller.ended)

        # Confirm quit -> forfeits
        inter_confirm = MockInteraction(2001, "pvp_btn_confirm_quit")
        asyncio.run(controller.execute_action({"type": "flee"}, actor_id="2001"))
        self.assertTrue(controller.ended)
        self.assertEqual(controller.p1_hp, 0)

    def test_phoenix_feather_auto_revive(self):
        """Verify player holding a Phoenix Feather survives lethal blow with 75% HP."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        # Give P1 a phoenix feather
        controller.p1_stats["inventory"]["phoenix_feather"] = 1
        controller.p1_hp = 50 # Low HP
        controller.active_id = "2002" # P2 strikes P1

        # High damage strike to trigger lethal damage
        controller.p1_rpg["spd"] = 1
        controller.p2_rpg["spd"] = 9999
        controller.p1_status["smoke"] = False
        controller.p2_rpg["atk"] = 99999
        res = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "mana_surge"}))

        self.assertIn("Phoenix Feather Auto-Revive", res)
        self.assertGreater(controller.p1_hp, 0)
        self.assertEqual(controller.p1_stats["inventory"].get("phoenix_feather", 0), 0)

    def test_secondary_status_effects_and_resist(self):
        """Verify secondary effects like Freeze and ATK buff apply and resolve."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        controller.active_id = "2001"

        # Apply frost nova with 100% stun chance
        controller.p1_skills.append({
            "id": "frost_nova", "name": "Frost Nova", "emoji": "❄️", "mp_cost": 20, "dmg_mult": 1.5, "stun_chance": 1.0
        })
        res = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "frost_nova"}))
        self.assertIn("Frozen", res)
        self.assertEqual(controller.p2_status["frozen"], 1)

        # Mystery class resistance check
        controller.p2_rpg["class_id"] = "mystery"
        res_resist = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "frost_nova"}))
        self.assertIn("resisted Freeze", res_resist)

    def test_fishing_style_select_dropdown_selection(self):
        """Verify selecting a skill from dropdown locks in skill."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )

        # Open skills menu ephemerally
        inter_open = MockInteraction(2001, "pvp_btn_open_skills")
        asyncio.run(yuna_pvp.handle_pvp_interaction(inter_open))

        # Select a skill via ephemeral interaction
        inter = MockInteraction(2001, "pvp_ephemeral_select_skill_2001", values=["wild_haymaker"])
        asyncio.run(yuna_pvp.handle_pvp_interaction(inter))

        self.assertIn("2001", controller.locked_actions)
        self.assertEqual(controller.locked_actions["2001"]["type"], "skill")
        self.assertEqual(controller.locked_actions["2001"]["skill_id"], "wild_haymaker")

    def test_opponent_cannot_see_or_use_other_player_skills(self):
        """Verify players cannot see opponent's skills in their menu and cannot lock in unowned opponent skills."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )

        # Player 1 (Brawler) skill view only contains P1 skills
        p1_skill_view = yuna_pvp.PvPSkillSelectView(controller, "2001")
        p1_select = [item for item in p1_skill_view.children if isinstance(item, yuna_pvp.Select)][0]
        p1_skill_ids = [opt.value for opt in p1_select.options]

        # Player 2 (Priest) skill view only contains P2 skills
        p2_skill_view = yuna_pvp.PvPSkillSelectView(controller, "2002")
        p2_select = [item for item in p2_skill_view.children if isinstance(item, yuna_pvp.Select)][0]
        p2_skill_ids = [opt.value for opt in p2_select.options]

        # P1 has brawler skills like brawler_strike / wild_haymaker, not lesser_heal
        self.assertIn("brawler_strike", p1_skill_ids)
        self.assertNotIn("lesser_heal", p1_skill_ids)

        # P2 has cleric/priest skills like lesser_heal, not brawler_strike
        self.assertIn("lesser_heal", p2_skill_ids)
        self.assertNotIn("brawler_strike", p2_skill_ids)

        # If P1 tries to illegally lock in P2's skill "lesser_heal", it is rejected
        illegal_inter = MockInteraction(2001, "pvp_ephemeral_select_skill_2001", values=["lesser_heal"])
        asyncio.run(controller.lock_in_action("2001", {"type": "skill", "skill_id": "lesser_heal"}, interaction=illegal_inter))

        self.assertNotIn("2001", controller.locked_actions)
        self.assertTrue(illegal_inter.response.is_done())
        sent = illegal_inter.response.sent_messages[0]
        self.assertIn("do not have the skill", sent["content"].lower())

    def test_all_secondary_status_effects_execution(self):
        """Verify secondary effects: Freeze, Stun, Attack Up, Defense Down, Poison II, Burn, Bleed, Lifesteal."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        controller.active_id = "2001"

        # 1. Attack Up (e.g. Battle Cry)
        battle_cry = {"id": "custom_battle_cry", "name": "Battle Cry", "mp_cost": 20, "dmg_mult": 1.0, "buff_next_atk": 1.25}
        controller.p1_skills.append(battle_cry)
        res_cry = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "custom_battle_cry"}))
        self.assertIn("ATK increased by 25%", res_cry)
        self.assertEqual(controller.p1_status["atk_buff"], 0.25)

        # 2. Defense Down (e.g. Sundering Cleave / Armor Strip)
        sunder = {"id": "cleave_edge", "name": "Sundering Cleave", "mp_cost": 20, "dmg_mult": 1.5, "armor_strip": 0.20}
        controller.p1_skills.append(sunder)
        res_sunder = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "cleave_edge"}))
        self.assertIn("DEF decreased by 20%", res_sunder)
        self.assertEqual(controller.p2_status["def_down"], 0.20)

        # 3. Poison II
        poison_sk = {"id": "toxic_dart", "name": "Toxic Dart", "mp_cost": 15, "dmg_mult": 1.2, "debuff": "poison"}
        controller.p1_skills.append(poison_sk)
        res_poison = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "toxic_dart"}))
        self.assertIn("Poison II", res_poison)
        self.assertEqual(controller.p2_status["poison"], 2)

        # 4. Burn
        burn_sk = {"id": "inferno", "name": "Inferno", "mp_cost": 20, "dmg_mult": 1.5, "debuff": "burn"}
        controller.p1_skills.append(burn_sk)
        res_burn = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "inferno"}))
        self.assertIn("Ignited", res_burn)
        self.assertEqual(controller.p2_status["burn"], 2)

        # 5. Bleed
        bleed_sk = {"id": "rend_artery", "name": "Arterial Rend", "mp_cost": 20, "dmg_mult": 1.5, "bleed": True}
        controller.p1_skills.append(bleed_sk)
        res_bleed = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "rend_artery"}))
        self.assertIn("Bleed", res_bleed)
        self.assertEqual(controller.p2_status["bleed"], 2)

        # 6. Stun (Physical CC)
        stun_sk = {"id": "shield_thump", "name": "Shield Thump", "mp_cost": 15, "dmg_mult": 1.2, "stun_chance": 1.0}
        controller.p1_skills.append(stun_sk)
        res_stun = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "shield_thump"}))
        self.assertIn("Stunned", res_stun)
        self.assertEqual(controller.p2_status["stunned"], 1)

        # 7. Lifesteal
        controller.p1_hp = 1000
        ls_sk = {"id": "vampiric_bite", "name": "Vampiric Bite", "mp_cost": 20, "dmg_mult": 2.0, "lifesteal": 0.50}
        controller.p1_skills.append(ls_sk)
        res_ls = asyncio.run(controller.execute_action({"type": "skill", "skill_id": "vampiric_bite"}))
        self.assertIn("Lifesteal", res_ls)
        self.assertGreater(controller.p1_hp, 1000)

    def test_simultaneous_both_players_lock_in_and_resolve_in_speed_order(self):
        """Verify both players lock in their skills first before firing, and resolve in SPD order."""
        controller = yuna_pvp.PvPBattleController(
            channel=self.chan,
            p1_user=self.p1,
            p2_user=self.p2,
            client=None,
            yuna_gambling_mod=yuna_gambling
        )
        controller.p1_rpg["spd"] = 500
        controller.p2_rpg["spd"] = 100

        # Player 1 locks in skill
        inter_p1 = MockInteraction(2001, "pvp_select_skill", values=["brawler_strike"])
        asyncio.run(yuna_pvp.handle_pvp_interaction(inter_p1))
        self.assertIn("2001", controller.locked_actions)
        self.assertNotIn("2002", controller.locked_actions)

        # Player 2 locks in skill
        inter_p2 = MockInteraction(2002, "pvp_select_skill", values=["lesser_heal"])
        asyncio.run(yuna_pvp.handle_pvp_interaction(inter_p2))
        self.assertIn("2002", controller.locked_actions)

        # Both players locked in -> resolve round
        p1_hp_before = controller.p1_hp
        p2_hp_before = controller.p2_hp
        asyncio.run(controller.resolve_locked_round())

        # P1 has higher speed, strikes first
        self.assertGreater(controller.p1_damage_dealt, 0)
        self.assertLess(controller.p2_hp, p2_hp_before)


if __name__ == "__main__":
    unittest.main()


