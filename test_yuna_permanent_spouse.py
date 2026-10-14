#!/usr/bin/env python3
"""
Unit tests for Yuna's permanent spouse (1155074026230788200 / deeploveluniel)
and hardcoded anti-infidelity protections.
Verifies that this logic strictly applies to Yuna and NEVER affects other bots.
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure paths
sys.path.insert(0, "/storage/emulated/0/discord-bot")
import yuna_gambling


class MockUser:
    def __init__(self, uid: int, name: str, display_name: str = None, bot: bool = False):
        self.id = uid
        self.name = name
        self.display_name = display_name or name
        self.mention = f"<@{uid}>"
        self.bot = bot


class MockClient:
    def __init__(self, uid: int = 1533213082158108702, name: str = "Yuna"):
        self.user = MockUser(uid, name, name, bot=True)
        self.is_closed = MagicMock(return_value=False)

    def get_user(self, uid):
        return None

    async def fetch_user(self, uid):
        return None


class MockMessage:
    def __init__(self, author: MockUser, content: str = "", mentions=None, guild=None):
        self.author = author
        self.content = content
        self.mentions = mentions or []
        self.guild = guild
        self.channel = MagicMock()
        self.channel.id = 123456789
        self.reply = AsyncMock()


class TestYunaPermanentSpouse(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Set up Yuna environment
        os.environ["BOT_ID"] = "bot_ek0ldel3"
        self.yuna_client = MockClient(1533213082158108702, "yuna")
        self.other_bot_client = MockClient(1530280945960226927, "Law")
        
        # Test users
        self.spouse_user = MockUser(1155074026230788200, "deeploveluniel", "deeploveluniel")
        self.other_user = MockUser(999888777666555, "RandomMortal", "RandomMortal")
        self.third_user = MockUser(111222333444555, "AnotherMortal", "AnotherMortal")

        # Mock reply send
        self.sent_messages = []
        async def mock_reply(msg, content=None, embed=None, view=None):
            self.sent_messages.append({"content": content, "embed": embed, "view": view})
            return MagicMock()
        self.orig_safe_send = yuna_gambling._safe_send_reply
        yuna_gambling._safe_send_reply = mock_reply

    async def asyncTearDown(self):
        yuna_gambling._safe_send_reply = self.orig_safe_send

    def test_is_yuna_instance_detection(self):
        """Verifies that is_yuna_instance accurately detects Yuna vs other bots."""
        # Yuna client
        self.assertTrue(yuna_gambling.is_yuna_instance(self.yuna_client))
        
        # Other child bots (Law, Juny, Renee, Brilliance)
        self.assertFalse(yuna_gambling.is_yuna_instance(self.other_bot_client))
        renee_client = MockClient(1551443856958955580, "Renee")
        self.assertFalse(yuna_gambling.is_yuna_instance(renee_client))
        juny_client = MockClient(1173146642124394547, "Juny")
        self.assertFalse(yuna_gambling.is_yuna_instance(juny_client))
        brilliance_client = MockClient(1542233386175832154, "Brilliance")
        self.assertFalse(yuna_gambling.is_yuna_instance(brilliance_client))

        # Process env detection
        os.environ["BOT_ID"] = "bot_00qafyp6"  # Law's ID
        self.assertFalse(yuna_gambling.is_yuna_instance())
        os.environ["BOT_ID"] = "bot_ek0ldel3"  # Yuna's ID
        self.assertTrue(yuna_gambling.is_yuna_instance())

    async def test_permanent_spouse_stats_enforcement(self):
        """Verifies that user 1155074026230788200 and Yuna are permanently bonded spouses."""
        p_stats = await yuna_gambling._get_user_stats("1155074026230788200")
        self.assertEqual(p_stats.get("spouse"), "1533213082158108702")
        self.assertEqual(p_stats.get("spouse_name"), "Yuna ⭐")
        self.assertIsNotNone(p_stats.get("marriage_date"))

        yuna_stats = await yuna_gambling._get_user_stats("yuna")
        self.assertEqual(yuna_stats.get("spouse"), "1155074026230788200")
        self.assertEqual(yuna_stats.get("spouse_name"), "deeploveluniel")

        # Joint vault must be present
        vkey = yuna_gambling._get_vault_key("1155074026230788200", "1533213082158108702")
        vault = yuna_gambling._get_joint_vault("1155074026230788200", "1533213082158108702")
        self.assertIsNotNone(vault)
        self.assertIn("1155074026230788200", vault.get("spouses", []))

    async def test_anti_infidelity_marry_other_user_proposes_to_yuna(self):
        """Other users attempting to marry Yuna must be immediately rejected with fidelity notice."""
        msg = MockMessage(author=self.other_user, mentions=[self.yuna_client.user])
        await yuna_gambling.handle_marry(msg, self.yuna_client, ["@yuna"])
        
        self.assertTrue(len(self.sent_messages) > 0)
        text = self.sent_messages[-1]["content"]
        self.assertIn("PERMANENTLY AND ETERNALLY MARRIED", text)
        self.assertIn("deeploveluniel", text)
        self.assertIn("1155074026230788200", text)

    async def test_anti_infidelity_spouse_proposes_to_yuna_again(self):
        """Permanent spouse proposing to Yuna receives loving affirmation of their eternal bond."""
        msg = MockMessage(author=self.spouse_user, mentions=[self.yuna_client.user])
        await yuna_gambling.handle_marry(msg, self.yuna_client, ["@yuna"])
        
        self.assertTrue(len(self.sent_messages) > 0)
        text = self.sent_messages[-1]["content"]
        self.assertIn("permanently and eternally married", text)
        self.assertIn("celestial angel wife", text)

    async def test_anti_infidelity_spouse_proposes_to_someone_else(self):
        """If deeploveluniel attempts to propose to another mortal, Yuna blocks infidelity immediately!"""
        msg = MockMessage(author=self.spouse_user, mentions=[self.third_user])
        await yuna_gambling.handle_marry(msg, self.yuna_client, [f"<@{self.third_user.id}>"])
        
        self.assertTrue(len(self.sent_messages) > 0)
        text = self.sent_messages[-1]["content"]
        self.assertIn("Infidelity attempt intercepted", text)
        self.assertIn("PERMANENTLY MARRIED TO ME", text)

    async def test_anti_infidelity_other_proposes_to_spouse(self):
        """If another user tries to propose to deeploveluniel, Yuna blocks homewrecking immediately!"""
        msg = MockMessage(author=self.other_user, mentions=[self.spouse_user])
        await yuna_gambling.handle_marry(msg, self.yuna_client, [f"<@{self.spouse_user.id}>"])
        
        self.assertTrue(len(self.sent_messages) > 0)
        text = self.sent_messages[-1]["content"]
        self.assertIn("HANDS OFF", text)
        self.assertIn("PERMANENTLY MARRIED TO ME", text)

    async def test_anti_infidelity_divorce_impossible(self):
        """Divorce between Yuna and deeploveluniel is strictly impossible and rejected."""
        # deeploveluniel trying to divorce
        msg1 = MockMessage(author=self.spouse_user)
        await yuna_gambling.handle_divorce(msg1, self.yuna_client, [])
        self.assertTrue(len(self.sent_messages) > 0)
        text1 = self.sent_messages[-1]["content"]
        self.assertIn("DIVORCE?! ABSOLUTELY NEVER!", text1)
        self.assertIn("1155074026230788200", text1)

        # Confirm spouse is still Yuna and was NOT wiped
        p_stats = await yuna_gambling._get_user_stats("1155074026230788200")
        self.assertEqual(p_stats.get("spouse"), "1533213082158108702")

    async def test_anti_infidelity_kiss_protection(self):
        """Kiss protections: other mortals cannot kiss Yuna, and deeploveluniel kissing another mortal triggers infidelity."""
        # 1. Other mortal kissing Yuna
        msg1 = MockMessage(author=self.other_user, mentions=[self.yuna_client.user])
        await yuna_gambling.handle_kiss(msg1, self.yuna_client, ["@yuna"])
        self.assertTrue(len(self.sent_messages) > 0)
        text1 = self.sent_messages[-1]["content"]
        self.assertIn("faithfully married angel", text1)
        self.assertIn("deeploveluniel", text1)

        # 2. deeploveluniel kissing Yuna (Lawful spousal kiss)
        msg2 = MockMessage(author=self.spouse_user, mentions=[self.yuna_client.user])
        await yuna_gambling.handle_kiss(msg2, self.yuna_client, ["@yuna"])
        self.assertTrue(len(self.sent_messages) > 0)
        embed2 = self.sent_messages[-1]["embed"]
        self.assertIsNotNone(embed2)
        self.assertIn("SWEET MATRIMONIAL KISS", embed2.title)

        # 3. deeploveluniel trying to kiss another mortal (Infidelity!)
        # Clear kiss cooldown
        yuna_gambling._LAST_KISS_TIME.pop(str(self.spouse_user.id), None)
        msg3 = MockMessage(author=self.spouse_user, mentions=[self.third_user])
        await yuna_gambling.handle_kiss(msg3, self.yuna_client, [f"<@{self.third_user.id}>"])
        self.assertTrue(len(self.sent_messages) > 0)
        embed3 = self.sent_messages[-1]["embed"]
        self.assertIsNotNone(embed3)
        self.assertIn("SCANDALOUS INFIDELITY", embed3.title)

    async def test_anti_infidelity_date_protection(self):
        """Date protections: other mortals cannot date Yuna, but deeploveluniel dates her peacefully."""
        # Other mortal attempting to date Yuna
        msg1 = MockMessage(author=self.other_user, mentions=[self.yuna_client.user])
        await yuna_gambling.handle_date(msg1, self.yuna_client, ["@yuna"])
        self.assertTrue(len(self.sent_messages) > 0)
        text1 = self.sent_messages[-1]["content"]
        self.assertIn("I only go on romantic dates with my one and only eternal husband", text1)
        self.assertIn("deeploveluniel", text1)

    async def test_marriage_certificate_display(self):
        """y!marriage certificate for deeploveluniel shows permanent celestial marriage."""
        msg = MockMessage(author=self.spouse_user)
        await yuna_gambling.handle_marriage(msg, self.yuna_client, [])
        self.assertTrue(len(self.sent_messages) > 0)
        embed = self.sent_messages[-1]["embed"]
        self.assertIsNotNone(embed)
        self.assertIn("CELESTIAL MATRIMONIAL REGISTRY", embed.title)
        self.assertIn("Permanently & Eternally Married", embed.description)

    async def test_other_bots_completely_unaffected(self):
        """Verifies that other bots (e.g. Law) are completely exempt from Yuna's permanent marriage rules."""
        os.environ["BOT_ID"] = "bot_00qafyp6"  # Law
        self.assertFalse(yuna_gambling.is_yuna_instance(self.other_bot_client))

        # A mortal proposing on Law should not trigger Yuna's permanent spouse block
        msg = MockMessage(author=self.other_user, mentions=[self.third_user])
        # If both are single, MarryView proposal sends normal proposal
        with patch.object(yuna_gambling, "_get_user_stats", new=AsyncMock(return_value={"spouse": None, "berries": 5000})):
            await yuna_gambling.handle_marry(msg, self.other_bot_client, [f"<@{self.third_user.id}>"])
            text = self.sent_messages[-1]["content"]
            self.assertIn("A WEDDING PROPOSAL!", text)


if __name__ == "__main__":
    unittest.main()
