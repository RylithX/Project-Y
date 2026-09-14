/**
 * mc_bridge.js — Advanced Autonomous Real-Player Minecraft Mineflayer Engine
 * Features:
 * - 3D A* Parkour Pathfinding & Locomotion (mineflayer-pathfinder)
 * - Intelligent Tool Selection (Pickaxe for stone/ores, Axe for wood, Shovel for dirt, Sword for PvP)
 * - Anti-Table Spam & Permanent Workstation (re-uses existing crafting tables, NEVER mines workbench)
 * - Strict Exposed Block Detection & Smart Subterranean Quarrying (digs dirt to reach stone bed)
 * - Direct Mining & Drop Collection Engine
 * - Multi-Step Recursive Auto-Crafting & Equipment Management
 * - Automated Furnace Smelting (Raw Iron -> Iron Ingots, Raw Meat -> Cooked Food)
 * - Animal Hunting & Dropped Meat/Wool Pickup
 * - Smart Bed Placement, Night Sleeping & Morning Recovery
 * - Persistent Journal, Dynamic Emergent Quests & Lifetime Stats
 * - Active Anti-AFK & Lively Human-like Player Immersion
 * - JSON IPC over stdin/stdout for Python Discord Bot
 */

const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');
const pvp = require('mineflayer-pvp').plugin;
const autoEat = require('mineflayer-auto-eat').loader;
const armorManager = require('mineflayer-armor-manager');
const { plugin: collectBlock } = require('mineflayer-collectblock');
const vec3 = require('vec3');
const readline = require('readline');
const fs = require('fs');
const path = require('path');

let opts = {};
try {
  opts = JSON.parse(process.argv[2] || '{}');
} catch (e) {
  opts = {};
}

// Global error handlers to prevent silent crashes
process.on('uncaughtException', (err) => {
  try { process.stdout.write(JSON.stringify({ type: 'error', msg: `[UNCAUGHT] ${err.message}` }) + '\n'); } catch(e) {}
});
process.on('unhandledRejection', (reason) => {
  try { process.stdout.write(JSON.stringify({ type: 'error', msg: `[UNHANDLED] ${reason}` }) + '\n'); } catch(e) {}
});

const MEMORIES_DIR = path.join(__dirname, 'memories', 'minecraft');
try {
  if (!fs.existsSync(MEMORIES_DIR)) fs.mkdirSync(MEMORIES_DIR, { recursive: true });
} catch (e) {}

const botId = (opts.botId || opts.username || 'default').replace(/[^a-zA-Z0-9_-]/g, '_');
const botName = opts.botName || opts.username || 'Bot';
const JOURNAL_FILE = path.join(MEMORIES_DIR, `${botId}_journal.json`);
const PID_DIR = path.join(__dirname, 'memories', 'pids');
try { if (!fs.existsSync(PID_DIR)) fs.mkdirSync(PID_DIR, { recursive: true }); } catch (e) {}
const MC_PID_FILE = path.join(PID_DIR, `mc_${botId}.pid`);

try {
  if (fs.existsSync(MC_PID_FILE)) {
    const oldPid = parseInt(fs.readFileSync(MC_PID_FILE, 'utf8').trim(), 10);
    if (oldPid && oldPid !== process.pid) {
      try {
        process.kill(oldPid, 'SIGKILL');
      } catch (e) {}
    }
  }
  fs.writeFileSync(MC_PID_FILE, String(process.pid));
} catch (e) {}

process.stdin.on('close', () => { process.exit(0); });
process.stdin.on('end', () => { process.exit(0); });

const bot = mineflayer.createBot({
  host: opts.host || 'localhost',
  port: parseInt(opts.port, 10) || 25565,
  username: opts.username || 'YunaBot',
  version: opts.version || false,
  auth: opts.auth || 'offline',
  checkTimeoutInterval: 120000,
  keepAlive: true,
  respawn: true
});

// Load plugins
bot.loadPlugin(pathfinder);
bot.loadPlugin(pvp);
bot.loadPlugin(autoEat);
bot.loadPlugin(armorManager);
bot.loadPlugin(collectBlock);

const rl = readline.createInterface({ input: process.stdin, output: null, terminal: false });

let defaultMove = null;
let currentTask = 'idle';
let currentTaskStartTime = Date.now();
let guardPos = null;
let followingTarget = null;
let lastGazeTime = 0;
let isInteracting = false;
let placedBedLocation = null;
let lastUserActivityTime = Date.now();
let autonomousEnabled = true;
let isExecutingProgression = false;

// ─── JOURNAL & DYNAMIC QUEST SYSTEM ────────────────────────

const DEFAULT_TODO_LIST = [
  { task: "Gather Wood Logs (4x)", done: false },
  { task: "Craft Crafting Table & Planks", done: false },
  { task: "Craft Wooden Pickaxe", done: false },
  { task: "Mine Cobblestone (8x)", done: false },
  { task: "Craft Stone Tools (Pickaxe, Sword, Axe)", done: false },
  { task: "Hunt Animals for Food & Wool", done: false },
  { task: "Craft Bed & Cook Food in Furnace", done: false },
  { task: "Mine Iron Ore & Coal", done: false },
  { task: "Smelt Iron & Craft Iron Armor & Shield", done: false },
  { task: "Explore Caves & Search for Diamonds", done: false }
];

const EXTENDED_QUESTS = [
  { task: "Build a Cozy Wooden Shelter with Door & Torches", done: false },
  { task: "Create a Farm Plot for Wheat & Carrots", done: false },
  { task: "Craft Full Iron Armor Set & Shield", done: false },
  { task: "Mine Deep Underground (Y < 0) for Diamonds", done: false },
  { task: "Craft Diamond Pickaxe & Diamond Sword", done: false },
  { task: "Gather Obsidian & Construct Nether Portal", done: false },
  { task: "Explore Nether Fortress & Defeat Blazes", done: false },
  { task: "Locate Stronghold & Prepare for Ender Dragon", done: false }
];

let journal = {
  todo_list: JSON.parse(JSON.stringify(DEFAULT_TODO_LIST)),
  milestones: [],
  lessons_learned: [
    "Always carry wood, pickaxe and torches when exploring caves.",
    "Raise shield immediately when hearing skeleton arrows.",
    "Keep at least 4.5 blocks distance when a creeper starts flashing.",
    "Dig topsoil to reach stone underground when no surface rock is visible."
  ],
  stats: {
    blocks_mined: 0,
    items_crafted: 0,
    mobs_defeated: 0,
    deaths: 0
  }
};

function loadJournal() {
  try {
    if (fs.existsSync(JOURNAL_FILE)) {
      const data = JSON.parse(fs.readFileSync(JOURNAL_FILE, 'utf8'));
      if (data && typeof data === 'object') {
        if (data.milestones) journal.milestones = data.milestones;
        if (data.lessons_learned) journal.lessons_learned = data.lessons_learned;
        if (data.stats) journal.stats = Object.assign(journal.stats, data.stats);
        if (Array.isArray(data.todo_list) && data.todo_list.length > 0) {
          journal.todo_list = data.todo_list;
        }
      }
    }
  } catch (e) {}
}
loadJournal();

function saveJournal() {
  try {
    fs.writeFileSync(JOURNAL_FILE, JSON.stringify(journal, null, 2), 'utf8');
  } catch (e) {}
}

function send(obj) {
  try {
    process.stdout.write(JSON.stringify(obj) + '\n');
  } catch (e) {}
}

function setTask(taskName) {
  currentTask = taskName;
  currentTaskStartTime = Date.now();
  send({ type: 'task_start', task: currentTask });
}

function clearTask(reason = null) {
  if (reason) {
    send({ type: 'task_failed', task: currentTask, reason });
  } else {
    send({ type: 'task_complete', task: currentTask });
  }
  currentTask = 'idle';
  currentTaskStartTime = Date.now();
  isExecutingProgression = false;
}

function logMilestone(desc) {
  const entry = {
    desc,
    time: new Date().toISOString(),
    pos: bot.entity ? { x: Math.round(bot.entity.position.x), y: Math.round(bot.entity.position.y), z: Math.round(bot.entity.position.z) } : null
  };
  journal.milestones.push(entry);
  if (journal.milestones.length > 50) journal.milestones.shift();
  saveJournal();
  send({ type: 'milestone', milestone: desc });
  send({ type: 'journal_data', journal });
}

function logLesson(lesson) {
  if (!journal.lessons_learned.includes(lesson)) {
    journal.lessons_learned.push(lesson);
    if (journal.lessons_learned.length > 30) journal.lessons_learned.shift();
    saveJournal();
  }
}

function completeTodo(taskKeywords) {
  if (!Array.isArray(taskKeywords)) taskKeywords = [taskKeywords];
  let changed = false;
  for (const item of journal.todo_list) {
    if (item.done) continue;
    for (const kw of taskKeywords) {
      if (item.task.toLowerCase().includes(kw.toLowerCase())) {
        item.done = true;
        changed = true;
        logMilestone(`Completed Goal: ${item.task}`);
        break;
      }
    }
  }
  if (changed) {
    checkDynamicTaskExpansion();
    saveJournal();
    send({ type: 'journal_data', journal });
  }
}

function checkDynamicTaskExpansion() {
  const completedCount = journal.todo_list.filter(t => t.done).length;
  const totalCount = journal.todo_list.length;
  if (completedCount >= totalCount - 2) {
    const existingTasks = journal.todo_list.map(t => t.task.toLowerCase());
    let added = false;
    for (const ext of EXTENDED_QUESTS) {
      if (!existingTasks.some(et => et.includes(ext.task.toLowerCase().slice(0, 10)))) {
        journal.todo_list.push(JSON.parse(JSON.stringify(ext)));
        added = true;
      }
    }
    if (added) {
      logMilestone(`Advanced to Next Survival Era: New quests unlocked!`);
      saveJournal();
    }
  }
}

function getInventoryList() {
  if (!bot.inventory) return [];
  return bot.inventory.items().map(i => ({
    name: i.name,
    count: i.count,
    slot: i.slot,
    displayName: i.displayName
  }));
}

function countItemInInventory(itemName) {
  if (!bot.inventory) return 0;
  return bot.inventory.items()
    .filter(i => i.name.toLowerCase().includes(itemName.toLowerCase()))
    .reduce((acc, i) => acc + i.count, 0);
}

function getNearbyPlayers() {
  if (!bot.entities) return [];
  const players = [];
  for (const id in bot.entities) {
    const e = bot.entities[id];
    if (e.type === 'player' && e.username && e.username !== bot.username) {
      players.push({
        username: e.username,
        pos: { x: Math.round(e.position.x), y: Math.round(e.position.y), z: Math.round(e.position.z) },
        distance: Math.round(bot.entity.position.distanceTo(e.position) * 10) / 10
      });
    }
  }
  return players;
}

function getNearbyMobs() {
  if (!bot.entities) return [];
  const mobs = [];
  for (const id in bot.entities) {
    const e = bot.entities[id];
    if (e.type === 'mob' || e.type === 'hostile') {
      const dist = bot.entity.position.distanceTo(e.position);
      if (dist < 24) {
        mobs.push({
          name: e.name || e.displayName || 'mob',
          type: e.type,
          distance: Math.round(dist * 10) / 10
        });
      }
    }
  }
  return mobs;
}

// ─── INTELLIGENT TOOL & WEAPON AUTO-EQUIPPER ────────────────

async function equipBestWeapon() {
  if (!bot.inventory) return;
  const weaponOrder = [
    'netherite_sword', 'diamond_sword', 'iron_sword', 'stone_sword', 'golden_sword', 'wooden_sword',
    'netherite_axe', 'diamond_axe', 'iron_axe', 'stone_axe', 'wooden_axe'
  ];
  for (const w of weaponOrder) {
    const item = bot.inventory.items().find(i => i.name === w);
    if (item) {
      try {
        await bot.equip(item, 'hand');
        return;
      } catch (e) {}
    }
  }
}

async function equipShield() {
  if (!bot.inventory) return;
  const shield = bot.inventory.items().find(i => i.name.includes('shield'));
  if (shield) {
    try {
      await bot.equip(shield, 'off-hand');
    } catch (e) {}
  }
}

async function equipBestTool(blockName) {
  if (!bot.inventory || !blockName) return;
  const norm = blockName.toLowerCase();
  let preferred = [];

  if (norm.includes('stone') || norm.includes('cobble') || norm.includes('ore') || norm.includes('deepslate') || norm.includes('furnace') || norm.includes('brick') || norm.includes('obsidian') || norm.includes('rock') || norm.includes('andesite') || norm.includes('diorite') || norm.includes('granite')) {
    preferred = ['netherite_pickaxe', 'diamond_pickaxe', 'iron_pickaxe', 'stone_pickaxe', 'wooden_pickaxe'];
  } else if (norm.includes('log') || norm.includes('wood') || norm.includes('stem') || norm.includes('planks') || norm.includes('crafting_table') || norm.includes('door') || norm.includes('chest') || norm.includes('fence')) {
    preferred = ['netherite_axe', 'diamond_axe', 'iron_axe', 'stone_axe', 'wooden_axe'];
  } else if (norm.includes('dirt') || norm.includes('grass') || norm.includes('sand') || norm.includes('gravel') || norm.includes('clay') || norm.includes('snow')) {
    preferred = ['netherite_shovel', 'diamond_shovel', 'iron_shovel', 'stone_shovel', 'wooden_shovel'];
  }

  for (const t of preferred) {
    const item = bot.inventory.items().find(i => i.name === t);
    if (item) {
      try {
        await bot.equip(item, 'hand');
        return;
      } catch (e) {}
    }
  }
}

async function equipBestArmorSet() {
  if (!bot.inventory) return;
  const armorTiers = {
    head: ['netherite_helmet', 'diamond_helmet', 'iron_helmet', 'golden_helmet', 'chainmail_helmet', 'leather_helmet'],
    torso: ['netherite_chestplate', 'diamond_chestplate', 'iron_chestplate', 'golden_chestplate', 'chainmail_chestplate', 'leather_chestplate'],
    legs: ['netherite_leggings', 'diamond_leggings', 'iron_leggings', 'golden_leggings', 'chainmail_leggings', 'leather_leggings'],
    feet: ['netherite_boots', 'diamond_boots', 'iron_boots', 'golden_boots', 'chainmail_boots', 'leather_boots']
  };

  for (const [slot, items] of Object.entries(armorTiers)) {
    for (const itemName of items) {
      const itm = bot.inventory.items().find(i => i.name === itemName);
      if (itm) {
        try {
          await bot.equip(itm, slot);
          break;
        } catch (e) {}
      }
    }
  }
  await equipShield();
}

// ─── SOCIAL & HUMAN BODY LANGUAGE EMOTES ────────────────────

async function performSneakSpam(count = 3) {
  if (isInteracting) return;
  isInteracting = true;
  for (let i = 0; i < count; i++) {
    bot.setControlState('sneak', true);
    await bot.waitForTicks(3);
    bot.setControlState('sneak', false);
    await bot.waitForTicks(3);
  }
  isInteracting = false;
}

async function performNod(count = 2) {
  if (isInteracting) return;
  isInteracting = true;
  const currentPitch = bot.entity.pitch;
  for (let i = 0; i < count; i++) {
    await bot.look(bot.entity.yaw, currentPitch + 0.5, true);
    await bot.waitForTicks(3);
    await bot.look(bot.entity.yaw, currentPitch - 0.3, true);
    await bot.waitForTicks(3);
  }
  await bot.look(bot.entity.yaw, currentPitch, true);
  isInteracting = false;
}

async function performShakeHead(count = 2) {
  if (isInteracting) return;
  isInteracting = true;
  const currentYaw = bot.entity.yaw;
  for (let i = 0; i < count; i++) {
    await bot.look(currentYaw + 0.6, bot.entity.pitch, true);
    await bot.waitForTicks(3);
    await bot.look(currentYaw - 0.6, bot.entity.pitch, true);
    await bot.waitForTicks(3);
  }
  await bot.look(currentYaw, bot.entity.pitch, true);
  isInteracting = false;
}

async function performJump() {
  bot.setControlState('jump', true);
  await bot.waitForTicks(4);
  bot.setControlState('jump', false);
}

// ─── BOT LIFECYCLE EVENTS ───────────────────────────────────

bot.on('login', () => {
  send({ type: 'login', username: bot.username });
});

bot.on('spawn', () => {
  const mcData = require('minecraft-data')(bot.version);
  defaultMove = new Movements(bot, mcData);
  defaultMove.canDig = true;
  defaultMove.allowParkour = true;
  defaultMove.allow1by1towers = true;
  defaultMove.allowFreeMotion = true;
  defaultMove.canOpenDoors = true;
  defaultMove.maxDropDown = 4;
  bot.pathfinder.setMovements(defaultMove);

  if (bot.autoEat) {
    bot.autoEat.options = {
      priority: 'foodPoints',
      startAt: 14,
      bannedFood: ['rotten_flesh', 'poisonous_potato', 'pufferfish', 'spider_eye', 'chorus_fruit']
    };
  }

  equipBestWeapon().catch(() => {});
  equipBestArmorSet().catch(() => {});

  send({
    type: 'spawn',
    username: bot.username,
    pos: { x: Math.round(bot.entity.position.x), y: Math.round(bot.entity.position.y), z: Math.round(bot.entity.position.z) },
    version: bot.version,
    journal
  });

  setTimeout(() => {
    if (autonomousEnabled && currentTask === 'idle' && !isExecutingProgression) {
      autonomousProgressionStep().catch(() => {});
    }
  }, 2500);

  if (opts.skin) {
    setTimeout(() => {
      try {
        bot.chat(`/skin set ${opts.skin}`);
      } catch (e) {}
    }, 2500);
  }
});

bot.on('chat', (username, message) => {
  if (username === bot.username) return;
  lastUserActivityTime = Date.now();
  send({ type: 'chat', username, message });

  const lower = message.toLowerCase();
  if (lower.includes(bot.username.toLowerCase()) || lower.includes('yuna') || lower.includes('law')) {
    if (lower.includes('hi') || lower.includes('hello') || lower.includes('hey')) {
      performSneakSpam(3);
    }
  }
});

bot.on('whisper', (username, message) => {
  if (username === bot.username) return;
  lastUserActivityTime = Date.now();
  send({ type: 'whisper', username, message });
});

bot.on('kicked', (reason) => {
  send({ type: 'kicked', reason: typeof reason === 'string' ? reason : JSON.stringify(reason) });
});

bot.on('error', (err) => {
  send({ type: 'error', msg: err.message });
});

bot.on('death', () => {
  currentTask = 'dead';
  journal.stats.deaths++;
  logLesson(`Died at ${bot.entity ? Math.round(bot.entity.position.x) + ',' + Math.round(bot.entity.position.y) + ',' + Math.round(bot.entity.position.z) : 'unknown'} -> Keep shield ready, watch health and maintain food level.`);
  saveJournal();
  send({ type: 'death' });
});

bot.on('end', () => {
  send({ type: 'end' });
  process.exit(0);
});

bot.on('health', () => {
  send({ type: 'health', health: bot.health, food: bot.food });
});

// Auto-defense on receiving damage
bot.on('entityHurt', async (entity) => {
  if (entity === bot.entity) {
    const attacker = bot.nearestEntity(e => (e.type === 'mob' || e.type === 'hostile' || e.type === 'player') && e !== bot.entity && e.position.distanceTo(bot.entity.position) < 14);
    if (attacker && !bot.pvp.target) {
      await equipBestWeapon();
      await equipShield();
      bot.pvp.attack(attacker);
      setTask(`defending against ${attacker.name || attacker.username}`);
    }
  }
});

// ─── TICK-BY-TICK REAL-PLAYER BEHAVIORS ──────────────────────

bot.on('physicsTick', () => {
  if (!bot.entity) return;

  // 1. Creeper Alert & Immediate Evasion
  if (bot.entities) {
    for (const id in bot.entities) {
      const e = bot.entities[id];
      if (e.name === 'creeper' || e.displayName === 'Creeper') {
        const dist = bot.entity.position.distanceTo(e.position);
        if (dist < 5.0) {
          bot.lookAt(e.position, true);
          bot.setControlState('sprint', true);
          bot.setControlState('back', true);
          setTimeout(() => {
            try {
              bot.setControlState('back', false);
              bot.setControlState('sprint', false);
            } catch(err) {}
          }, 900);
          return;
        }
      }
    }
  }

  // 2. Shield Defense against projectile mobs
  const skeleton = bot.nearestEntity(e => (e.name === 'skeleton' || e.name === 'pillager' || e.name === 'stray') && e.position.distanceTo(bot.entity.position) < 16);
  if (skeleton && bot.inventory) {
    const hasShield = bot.inventory.items().some(i => i.name.includes('shield'));
    if (hasShield) {
      bot.setControlState('sneak', true);
    }
  } else if (!isInteracting && currentTask === 'idle') {
    bot.setControlState('sneak', false);
  }

  // 3. Guard mode patrol
  if (currentTask === 'guard' && guardPos) {
    const mob = bot.nearestEntity(e => (e.type === 'mob' || e.type === 'hostile') && e.position.distanceTo(guardPos) < 18);
    if (mob && !bot.pvp.target) {
      equipBestWeapon().catch(() => {});
      bot.pvp.attack(mob);
    } else if (!mob && bot.pvp.target) {
      bot.pvp.stop();
      bot.pathfinder.setGoal(new goals.GoalNear(guardPos.x, guardPos.y, guardPos.z, 2));
    }
  }

  // 4. Human Idle Look & Gaze at Nearby Players
  const now = Date.now();
  if (currentTask === 'idle' && !isInteracting && now - lastGazeTime > 3500) {
    lastGazeTime = now;
    const player = bot.nearestEntity(e => e.type === 'player' && e.username !== bot.username);
    if (player && bot.entity.position.distanceTo(player.position) < 6) {
      bot.lookAt(player.position.offset(0, 1.6, 0), false);
    } else if (Math.random() < 0.25) {
      const randomYaw = bot.entity.yaw + (Math.random() - 0.5) * 1.2;
      const randomPitch = (Math.random() - 0.5) * 0.4;
      bot.look(randomYaw, randomPitch, false);
    }
  }
});

// ─── RECURSIVE SMART CRAFTING ENGINE ────────────────────────

async function craftWithTimeout(recipe, count = 1, tableBlock = null, timeoutMs = 6000) {
  if (!recipe) return false;
  try { bot.pathfinder.stop(); } catch (e) {}

  if (tableBlock) {
    const dist = bot.entity.position.distanceTo(tableBlock.position);
    if (dist > 3.5) {
      try {
        await bot.pathfinder.goto(new goals.GoalNear(tableBlock.position.x, tableBlock.position.y, tableBlock.position.z, 2));
      } catch (e) {}
    }
    await bot.lookAt(tableBlock.position.offset(0.5, 0.5, 0.5), true);
  }

  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      resolve(false);
    }, timeoutMs);
    bot.craft(recipe, count, tableBlock)
      .then(() => {
        clearTimeout(timer);
        resolve(true);
      })
      .catch(() => {
        clearTimeout(timer);
        resolve(false);
      });
  });
}

async function placeBlockSafely(item) {
  if (!bot.entity) return null;
  const botFloor = bot.entity.position.floored();
  const offsets = [
    new vec3(1, -1, 0),
    new vec3(-1, -1, 0),
    new vec3(0, -1, 1),
    new vec3(0, -1, -1),
    new vec3(1, 0, 0),
    new vec3(-1, 0, 0),
    new vec3(0, 0, 1),
    new vec3(0, 0, -1)
  ];

  let referenceBlock = null;
  let targetAirPos = null;

  for (const off of offsets) {
    const candidate = bot.blockAt(botFloor.plus(off));
    if (candidate && candidate.type !== 0 && candidate.boundingBox === 'block') {
      const airPos = candidate.position.offset(0, 1, 0);
      const airBlock = bot.blockAt(airPos);
      if (airBlock && (airBlock.type === 0 || airBlock.name === 'air') && !airPos.equals(botFloor) && !airPos.equals(botFloor.offset(0, 1, 0))) {
        referenceBlock = candidate;
        targetAirPos = airPos;
        break;
      }
    }
  }

  if (!referenceBlock) return null;

  try {
    await bot.equip(item, 'hand');
    await bot.lookAt(referenceBlock.position.offset(0.5, 0.5, 0.5), true);
    await Promise.race([
      bot.placeBlock(referenceBlock, new vec3(0, 1, 0)),
      new Promise((_, reject) => setTimeout(() => reject(new Error('placeBlock timeout')), 3000))
    ]);
    await bot.waitForTicks(4);
    return targetAirPos;
  } catch (e) {
    return null;
  }
}

async function ensurePlanks(count = 4) {
  const planksCount = countItemInInventory('planks');
  if (planksCount >= count) return true;
  const mcData = require('minecraft-data')(bot.version);
  const logItem = bot.inventory.items().find(i => i.name.includes('log') || i.name.includes('wood') || i.name.includes('stem'));
  if (!logItem) return false;
  const plankName = logItem.name.replace('_log', '_planks').replace('_wood', '_planks').replace('_stem', '_planks');
  const plankItem = mcData.itemsByName[plankName] || mcData.itemsByName['oak_planks'] || mcData.itemsByName['planks'];
  if (!plankItem) return false;
  const recipes = bot.recipesFor(plankItem.id, null, 1, null);
  if (recipes && recipes.length > 0) {
    const craftCount = Math.ceil((count - planksCount) / 4);
    const ok = await craftWithTimeout(recipes[0], craftCount, null);
    if (ok) {
      journal.stats.items_crafted += craftCount * 4;
      completeTodo(["Planks", "Craft Crafting Table"]);
      return true;
    }
  }
  return false;
}

async function ensureSticks(count = 4) {
  const stickCount = countItemInInventory('stick');
  if (stickCount >= count) return true;
  if (countItemInInventory('planks') < 2) {
    await ensurePlanks(2);
  }
  const mcData = require('minecraft-data')(bot.version);
  const stickItem = mcData.itemsByName['stick'];
  if (!stickItem) return false;
  const recipes = bot.recipesFor(stickItem.id, null, 1, null);
  if (recipes && recipes.length > 0) {
    const craftCount = Math.ceil((count - stickCount) / 4);
    const ok = await craftWithTimeout(recipes[0], craftCount, null);
    if (ok) {
      journal.stats.items_crafted += craftCount * 4;
      return true;
    }
  }
  return false;
}

// Re-uses existing crafting tables in world without placing or crafting new ones!
async function ensureCraftingTablePlaced() {
  const mcData = require('minecraft-data')(bot.version);
  const tableBlockId = mcData.blocksByName.crafting_table ? mcData.blocksByName.crafting_table.id : null;
  if (!tableBlockId) return { block: null };

  // 1. Search for existing table within 32 blocks
  let tableBlock = bot.findBlock({ matching: tableBlockId, maxDistance: 32 });
  if (tableBlock) {
    return { block: tableBlock };
  }

  // 2. Check if crafting table in inventory
  let tableItem = bot.inventory.items().find(i => i.name === 'crafting_table');
  if (!tableItem) {
    await ensurePlanks(4);
    const tableRecipeItem = mcData.itemsByName['crafting_table'];
    if (tableRecipeItem) {
      const recipes = bot.recipesFor(tableRecipeItem.id, null, 1, null);
      if (recipes && recipes.length > 0) {
        await craftWithTimeout(recipes[0], 1, null);
        journal.stats.items_crafted++;
        completeTodo(["Crafting Table", "Planks"]);
        tableItem = bot.inventory.items().find(i => i.name === 'crafting_table');
      }
    }
  }
  if (!tableItem) return { block: null };

  // 3. Place table safely — keep it permanently in the world as a workbench!
  const placedPos = await placeBlockSafely(tableItem);
  if (placedPos) {
    tableBlock = bot.blockAt(placedPos);
    return { block: tableBlock };
  } else {
    tableBlock = bot.findBlock({ matching: tableBlockId, maxDistance: 6 });
    return { block: tableBlock };
  }
}

async function handleCraft(itemName, count = 1) {
  setTask(`crafting ${count} ${itemName}`);
  lastUserActivityTime = Date.now();
  try {
    const mcData = require('minecraft-data')(bot.version);
    const cleanName = itemName.toLowerCase().replace(/ /g, '_');
    const targetItem = mcData.itemsByName[cleanName];
    if (!targetItem) {
      clearTask(`Unknown item: ${itemName}`);
      return false;
    }

    const name = targetItem.name;
    if (name.includes('pickaxe') || name.includes('axe') || name.includes('sword') || name.includes('shovel') || name.includes('hoe')) {
      const sticksNeeded = name.includes('sword') ? count : (2 * count);
      await ensureSticks(sticksNeeded);
    }
    if (name.startsWith('wooden_')) {
      await ensurePlanks(3 * count);
    }
    if (name.includes('torch')) {
      await ensureSticks(count);
    }

    // Check recipes in 2x2 player crafting grid
    let recipes = bot.recipesFor(targetItem.id, null, count, null);
    if (recipes && recipes.length > 0) {
      const ok = await craftWithTimeout(recipes[0], count, null);
      if (ok) {
        journal.stats.items_crafted += count;
        logMilestone(`Crafted ${count} ${targetItem.name}`);
        completeTodo([targetItem.name, name]);
        clearTask();
        return true;
      }
    }

    // 3x3 Crafting table required
    const { block: tableBlock } = await ensureCraftingTablePlaced();
    if (!tableBlock) {
      clearTask(`Could not find or place crafting table for ${itemName}`);
      return false;
    }

    try {
      await bot.pathfinder.goto(new goals.GoalNear(tableBlock.position.x, tableBlock.position.y, tableBlock.position.z, 2));
    } catch(e) {}

    recipes = bot.recipesFor(targetItem.id, null, count, tableBlock);
    if (!recipes || recipes.length === 0) {
      clearTask(`Missing ingredients to craft ${itemName}`);
      return false;
    }

    const ok = await craftWithTimeout(recipes[0], count, tableBlock);
    if (ok) {
      journal.stats.items_crafted += count;
      logMilestone(`Crafted ${count} ${targetItem.name}`);
      completeTodo([targetItem.name, name]);

      if (name.includes('pickaxe') || name.includes('sword') || name.includes('axe')) {
        await equipBestWeapon();
        await equipBestTool(name);
      }
      if (name.includes('shield')) await equipShield();
      if (name.includes('helmet') || name.includes('chestplate') || name.includes('leggings') || name.includes('boots')) await equipBestArmorSet();

      clearTask();
      return true;
    } else {
      clearTask(`Table crafting timed out for ${itemName}`);
      return false;
    }
  } catch (err) {
    clearTask(err.message);
    return false;
  }
}

// ─── FURNACE SMELTING ENGINE ────────────────────────────────

async function handleSmelt(inputItemName, fuelItemName = 'coal', count = 1) {
  setTask(`smelting ${count} ${inputItemName}`);
  lastUserActivityTime = Date.now();
  try {
    const mcData = require('minecraft-data')(bot.version);
    const furnaceBlockId = mcData.blocksByName.furnace ? mcData.blocksByName.furnace.id : null;
    if (!furnaceBlockId) {
      clearTask('Furnace block not supported');
      return false;
    }

    let furnaceBlock = bot.findBlock({ matching: furnaceBlockId, maxDistance: 32 });

    if (!furnaceBlock) {
      let furnaceItem = bot.inventory.items().find(i => i.name === 'furnace');
      if (!furnaceItem) {
        const cobbleCount = countItemInInventory('cobblestone') + countItemInInventory('stone');
        if (cobbleCount < 8) {
          await handleMineBlock('stone', 8 - cobbleCount);
        }
        await handleCraft('furnace', 1);
        furnaceItem = bot.inventory.items().find(i => i.name === 'furnace');
      }
      if (furnaceItem) {
        const placedPos = await placeBlockSafely(furnaceItem);
        if (placedPos) {
          furnaceBlock = bot.blockAt(placedPos);
        }
      }
    }

    if (!furnaceBlock) {
      clearTask('Could not place or locate furnace');
      return false;
    }

    await bot.pathfinder.goto(new goals.GoalNear(furnaceBlock.position.x, furnaceBlock.position.y, furnaceBlock.position.z, 2));

    const furnace = await bot.openFurnace(furnaceBlock);
    const inputItem = bot.inventory.items().find(i => i.name.toLowerCase().includes(inputItemName.toLowerCase()));
    let fuelItem = bot.inventory.items().find(i => i.name === 'coal' || i.name === 'charcoal' || i.name.includes('planks') || i.name.includes('log'));

    if (!inputItem) {
      furnace.close();
      clearTask(`No ${inputItemName} to smelt in inventory`);
      return false;
    }

    if (!fuelItem) {
      await ensurePlanks(4);
      fuelItem = bot.inventory.items().find(i => i.name.includes('planks'));
    }

    if (fuelItem) await furnace.putFuel(fuelItem.type, null, Math.min(fuelItem.count, 4));
    await furnace.putInput(inputItem.type, null, Math.min(inputItem.count, count));

    await bot.waitForTicks(100);

    try {
      if (furnace.outputItem()) {
        await furnace.takeOutput();
      }
    } catch (e) {}

    furnace.close();

    logMilestone(`Smelted ${inputItemName} in furnace`);
    completeTodo(["Smelt Iron", "Cook Food", "Furnace"]);
    clearTask();
    return true;
  } catch (err) {
    clearTask(err.message);
    return false;
  }
}

// ─── ANIMAL HUNTING & DROP PICKUP ───────────────────────────

async function collectNearbyDroppedItems(radius = 12) {
  if (!bot.entities) return;
  for (const id in bot.entities) {
    const e = bot.entities[id];
    if (e.type === 'object' || e.name === 'item' || (e.displayName && e.displayName.toLowerCase().includes('item'))) {
      const dist = bot.entity.position.distanceTo(e.position);
      if (dist < radius) {
        try {
          await Promise.race([
            bot.pathfinder.goto(new goals.GoalNear(e.position.x, e.position.y, e.position.z, 1)),
            new Promise(r => setTimeout(r, 2500))
          ]);
          await bot.waitForTicks(2);
        } catch (e) {}
      }
    }
  }
}

async function handleHuntAnimals(count = 2) {
  setTask(`hunting animals for food & wool`);
  lastUserActivityTime = Date.now();
  let hunted = 0;
  try {
    for (let i = 0; i < count; i++) {
      const animal = bot.nearestEntity(e => (e.name === 'cow' || e.name === 'pig' || e.name === 'sheep' || e.name === 'chicken') && e.position.distanceTo(bot.entity.position) < 32);
      if (!animal) {
        await exploreArea(20);
        continue;
      }
      await equipBestWeapon();
      bot.pvp.attack(animal);

      await new Promise(resolve => {
        const checkInterval = setInterval(() => {
          if (!animal.isValid || animal.health <= 0 || !bot.pvp.target) {
            clearInterval(checkInterval);
            bot.pvp.stop();
            resolve();
          }
        }, 500);
        setTimeout(() => {
          clearInterval(checkInterval);
          bot.pvp.stop();
          resolve();
        }, 12000);
      });

      hunted++;
      await collectNearbyDroppedItems(12);
    }

    if (hunted > 0) {
      logMilestone(`Hunted ${hunted} animals for food and supplies`);
      completeTodo(["Hunt Animals", "Food", "Wool"]);
      clearTask();
    } else {
      clearTask('No animals found nearby');
    }
  } catch (err) {
    clearTask(err.message);
  }
}

// ─── SMART BED PLACEMENT & SLEEPING ENGINE ──────────────────

async function handleSleep() {
  setTask('sleeping through night');
  lastUserActivityTime = Date.now();
  try {
    let bedBlock = bot.findBlock({
      matching: block => bot.isABed(block),
      maxDistance: 24
    });

    if (!bedBlock) {
      let bedItem = bot.inventory.items().find(i => i.name.includes('_bed') || i.name === 'bed');
      if (!bedItem) {
        const woolCount = countItemInInventory('wool');
        const planksCount = countItemInInventory('planks');
        if (woolCount >= 3 && planksCount >= 3) {
          await handleCraft('white_bed', 1);
          bedItem = bot.inventory.items().find(i => i.name.includes('_bed') || i.name === 'bed');
        }
      }

      if (bedItem) {
        const floorBlock = bot.findBlock({
          matching: block => block.type !== 0 && block.boundingBox === 'block',
          maxDistance: 3,
          point: bot.entity.position
        });
        if (floorBlock) {
          await bot.equip(bedItem, 'hand');
          await bot.placeBlock(floorBlock, new vec3(0, 1, 0));
          await bot.waitForTicks(8);
          bedBlock = bot.findBlock({ matching: block => bot.isABed(block), maxDistance: 6 });
          if (bedBlock) placedBedLocation = bedBlock.position.clone();
        }
      }
    }

    if (!bedBlock) {
      clearTask('No bed placed nearby and insufficient materials for bed.');
      return;
    }

    await bot.pathfinder.goto(new goals.GoalGetToBlock(bedBlock.position.x, bedBlock.position.y, bedBlock.position.z));
    await bot.sleep(bedBlock);
    completeTodo(["Bed", "Sleep"]);
    logMilestone("Slept safely through the night");
    clearTask();
  } catch (err) {
    clearTask(err.message);
  }
}

bot.on('wake', async () => {
  if (placedBedLocation) {
    try {
      const bedBlock = bot.blockAt(placedBedLocation);
      if (bedBlock && bot.isABed(bedBlock)) {
        await equipBestTool('bed');
        await bot.dig(bedBlock);
        await collectNearbyDroppedItems(4);
        placedBedLocation = null;
      }
    } catch (e) {}
  }
});

// ─── SMART PROXIMITY ITEM GIVING ENGINE ─────────────────────

async function handleGive(username, itemName, count = 1) {
  setTask(`giving ${count} ${itemName} to ${username}`);
  lastUserActivityTime = Date.now();
  try {
    let targetPlayer = null;
    if (!username || username === 'me' || username === 'player') {
      const nearby = getNearbyPlayers();
      if (nearby.length > 0) username = nearby[0].username;
    }

    for (const p in bot.players) {
      if (p.toLowerCase() === (username || '').toLowerCase()) {
        targetPlayer = bot.players[p];
        break;
      }
    }

    if (!targetPlayer || !targetPlayer.entity) {
      clearTask(`Player '${username}' is not nearby in render distance.`);
      return;
    }

    await bot.pathfinder.goto(new goals.GoalFollow(targetPlayer.entity, 2));

    const itemLower = (itemName || '').toLowerCase();
    const itemsToDrop = bot.inventory.items().filter(i => itemLower === 'all' || i.name.toLowerCase().includes(itemLower) || i.displayName.toLowerCase().includes(itemLower));

    if (itemsToDrop.length === 0) {
      clearTask(`I don't have any '${itemName}' in my inventory.`);
      return;
    }

    await bot.lookAt(targetPlayer.entity.position.offset(0, 1.3, 0), true);
    for (const itm of itemsToDrop) {
      const dropAmount = itemLower === 'all' ? itm.count : Math.min(itm.count, count);
      await bot.toss(itm.type, null, dropAmount);
      await bot.waitForTicks(3);
    }

    await performSneakSpam(2);
    logMilestone(`Gave ${count} ${itemName} to ${targetPlayer.username}`);
    clearTask();
  } catch (err) {
    clearTask(err.message);
  }
}

// ─── EXPOSED BLOCK DETECTION & SMART DIGGING ────────────────

function isBlockExposed(block) {
  if (!block || !block.position) return false;
  try {
    const offsets = [
      new vec3(0, 1, 0),
      new vec3(0, -1, 0),
      new vec3(1, 0, 0),
      new vec3(-1, 0, 0),
      new vec3(0, 0, 1),
      new vec3(0, 0, -1)
    ];
    for (const off of offsets) {
      const adj = bot.blockAt(block.position.plus(off));
      if (!adj || adj.type === 0 || adj.name === 'air' || adj.name === 'cave_air' || adj.name === 'water' || adj.boundingBox !== 'block') {
        return true;
      }
    }
  } catch (e) {
    return false;
  }
  return false;
}

function findMineableBlock(matcher, maxDistance = 48) {
  try {
    return bot.findBlock({
      matching: (b) => {
        try {
          return matcher(b) && isBlockExposed(b);
        } catch (e) {
          return false;
        }
      },
      maxDistance: maxDistance
    });
  } catch (e) {
    return null;
  }
}

// For blocks like logs/trees that don't need exposure checks
function findAnyBlock(matcher, maxDistance = 48) {
  try {
    return bot.findBlock({
      matching: (b) => {
        try { return matcher(b); } catch (e) { return false; }
      },
      maxDistance: maxDistance
    });
  } catch (e) {
    return null;
  }
}

function getBlockMatcher(blockName) {
  const norm = (blockName || '').toLowerCase().replace(/ /g, '_');
  if (norm.includes('log') || norm.includes('wood') || norm === 'tree') {
    return b => b.name.includes('_log') || b.name.includes('_wood') || b.name.includes('stem');
  }
  if (norm === 'stone' || norm === 'cobblestone' || norm === 'rock') {
    return b => b.name === 'stone' || b.name === 'cobblestone' || b.name === 'deepslate' || b.name === 'cobbled_deepslate' || b.name === 'andesite' || b.name === 'diorite' || b.name === 'granite';
  }
  if (norm.includes('iron')) {
    return b => b.name.includes('iron_ore') || b.name === 'raw_iron_block';
  }
  if (norm.includes('coal')) {
    return b => b.name.includes('coal_ore');
  }
  if (norm.includes('copper')) {
    return b => b.name.includes('copper_ore');
  }
  if (norm.includes('diamond')) {
    return b => b.name.includes('diamond_ore');
  }
  if (norm.includes('gold')) {
    return b => b.name.includes('gold_ore');
  }
  try {
    const mcData = require('minecraft-data')(bot.version);
    const blockType = mcData.blocksByName[norm];
    if (blockType) return b => b.type === blockType.id;
  } catch (e) {}
  return b => b.name.includes(norm);
}

// Single block miner with direct reach, look, dig, and item vacuum
async function mineSingleBlock(targetBlock) {
  if (!targetBlock) return false;

  await equipBestTool(targetBlock.name);

  const dist = bot.entity.position.distanceTo(targetBlock.position.offset(0.5, 0.5, 0.5));
  if (dist > 4.0) {
    try {
      await Promise.race([
        bot.pathfinder.goto(new goals.GoalNear(targetBlock.position.x, targetBlock.position.y, targetBlock.position.z, 3)),
        new Promise((_, reject) => setTimeout(() => {
          try { bot.pathfinder.stop(); } catch(e) {}
          reject(new Error('Path timeout'));
        }, 7000))
      ]);
    } catch (e) {}
  }

  const blockCenter = targetBlock.position.offset(0.5, 0.5, 0.5);
  try {
    await bot.lookAt(blockCenter, true);
    await equipBestTool(targetBlock.name);

    if (bot.canDigBlock(targetBlock)) {
      await bot.dig(targetBlock);
      await bot.waitForTicks(3);
      await collectNearbyDroppedItems(6);
      return true;
    }
  } catch (digErr) {
    try {
      await Promise.race([
        bot.collectBlock.collect(targetBlock),
        new Promise((_, reject) => setTimeout(() => {
          try { bot.pathfinder.stop(); } catch(e) {}
          reject(new Error('Collect timeout'));
        }, 7000))
      ]);
      return true;
    } catch (cbErr) {
      return false;
    }
  }
  return false;
}

// Intelligently digs down through topsoil/dirt to reach stone underneath when no surface rock exists
async function digDownToStone(count = 8) {
  if (!bot.entity) return 0;
  let minedStone = 0;

  // Dig a 1x1 shaft straight down in front of the bot, clearing dirt until we hit stone
  // Then mine the stone we find. Max 15 blocks deep to cover most overworld terrain.
  const startPos = bot.entity.position.floored();
  const forward = bot.entity.position.offset(1, 0, 0).floored();

  // First dig forward one block so we have a pit entrance
  const entranceBlock = bot.blockAt(forward);
  if (entranceBlock && entranceBlock.type !== 0 && entranceBlock.name !== 'air') {
    try {
      await equipBestTool(entranceBlock.name);
      await bot.lookAt(forward.offset(0.5, 0.5, 0.5), true);
      await bot.dig(entranceBlock);
      await bot.waitForTicks(3);
    } catch (e) {}
  }

  // Dig straight down from current position, layer by layer
  for (let dy = 1; dy <= 15; dy++) {
    if (minedStone >= count) break;

    // Dig the block below us
    const digPos = startPos.offset(0, -dy, 0);
    const blk = bot.blockAt(digPos);
    if (!blk || blk.type === 0 || blk.name === 'air') continue;
    if (blk.name === 'water' || blk.name === 'lava' || blk.name === 'flowing_water' || blk.name === 'flowing_lava') {
      send({ type: 'progress', task: currentTask, progress: 'Hit liquid, stopping shaft' });
      break;
    }
    if (blk.name === 'bedrock') break;

    const isStone = blk.name.includes('stone') || blk.name.includes('cobble') || blk.name.includes('deepslate') || blk.name.includes('andesite') || blk.name.includes('diorite') || blk.name.includes('granite');

    await equipBestTool(blk.name);
    try {
      await bot.lookAt(digPos.offset(0.5, 0.5, 0.5), true);
      if (bot.canDigBlock(blk)) {
        await bot.dig(blk);
        await bot.waitForTicks(3);
        await collectNearbyDroppedItems(5);

        if (isStone) {
          minedStone++;
          journal.stats.blocks_mined++;
          completeTodo(["Cobblestone", "Mine Cobblestone", "Stone"]);
          send({ type: 'progress', task: currentTask, progress: `Quarried ${minedStone}/${count} stone` });
        }
      }
    } catch (e) {}
  }

  // Mine exposed stone around the shaft hole we just made
  if (minedStone < count) {
    const stoneMatcher = getBlockMatcher('stone');
    for (let i = 0; i < (count - minedStone) + 5; i++) {
      const exposed = findMineableBlock(stoneMatcher, 8);
      if (!exposed) break;

      try {
        await equipBestTool(exposed.name);
        await bot.lookAt(exposed.position.offset(0.5, 0.5, 0.5), true);
        const dist = bot.entity.position.distanceTo(exposed.position);
        if (dist > 4.5) {
          await Promise.race([
            bot.pathfinder.goto(new goals.GoalNear(exposed.position.x, exposed.position.y, exposed.position.z, 3)),
            new Promise(r => setTimeout(() => { try { bot.pathfinder.stop(); } catch(e){} r(); }, 5000))
          ]);
        }
        if (bot.canDigBlock(exposed)) {
          await bot.dig(exposed);
          await bot.waitForTicks(3);
          await collectNearbyDroppedItems(5);
          minedStone++;
          journal.stats.blocks_mined++;
        }
      } catch (e) {}

      if (minedStone >= count) break;
    }
  }

  return minedStone;
}

async function exploreArea(distance = 25) {
  if (!bot.entity) return;
  const angle = Math.random() * Math.PI * 2;
  const targetX = Math.round(bot.entity.position.x + Math.cos(angle) * distance);
  const targetZ = Math.round(bot.entity.position.z + Math.sin(angle) * distance);

  setTask(`roaming/exploring world (${targetX}, ${targetZ})`);
  try {
    const goal = new goals.GoalNearXZ(targetX, targetZ, 3);
    await Promise.race([
      bot.pathfinder.goto(goal),
      new Promise((resolve) => setTimeout(() => {
        try { bot.pathfinder.stop(); } catch(e) {}
        resolve();
      }, 10000))
    ]);
  } catch (e) {}
  currentTask = 'idle';
}

async function handleMineBlock(blockName, count = 1) {
  setTask(`mining ${count} ${blockName}`);
  lastUserActivityTime = Date.now();
  try {
    const matcher = getBlockMatcher(blockName);
    const isStoneType = blockName.includes('stone') || blockName.includes('cobble');
    const isLogType = blockName.includes('log') || blockName.includes('wood') || blockName === 'tree';
    let collected = 0;

    // For stone: try exposed first, then quarry down
    if (isStoneType) {
      let exposedStone = findMineableBlock(matcher, 36);
      if (!exposedStone) {
        send({ type: 'progress', task: currentTask, progress: 'No surface stone - quarrying down through dirt...' });
        const mined = await digDownToStone(count);
        collected += mined;
      }
    }

    while (collected < count) {
      // Logs/trees: use findAnyBlock (no exposure check)
      // Stone/ores: use findMineableBlock (exposed only)
      let targetBlock = isLogType ? findAnyBlock(matcher, 64) : findMineableBlock(matcher, 48);

      if (!targetBlock) {
        // Try exploring to find blocks
        send({ type: 'progress', task: currentTask, progress: `Searching for ${blockName}...` });
        await exploreArea(30);
        targetBlock = isLogType ? findAnyBlock(matcher, 64) : findMineableBlock(matcher, 48);

        if (!targetBlock && isStoneType) {
          const mined = await digDownToStone(count - collected);
          collected += mined;
        }
        if (!targetBlock) {
          if (collected > 0) break;
          clearTask(`No ${blockName} found in current area.`);
          return;
        }
      }

      if (!targetBlock) break;

      // Try collectBlock first (handles pathing + digging + pickup)
      let minedOk = false;
      try {
        await equipBestTool(targetBlock.name);
        await Promise.race([
          bot.collectBlock.collect(targetBlock),
          new Promise((_, reject) => setTimeout(() => {
            try { bot.pathfinder.stop(); } catch(e) {}
            reject(new Error('collect timeout'));
          }, 12000))
        ]);
        minedOk = true;
      } catch (collectErr) {
        // Fallback: try direct mining
        minedOk = await mineSingleBlock(targetBlock);
      }

      if (minedOk) {
        collected++;
        journal.stats.blocks_mined++;
        send({ type: 'progress', task: currentTask, progress: `${collected}/${count}` });
      } else {
        // Don't get stuck on one unmineableable block, try another one
        send({ type: 'progress', task: currentTask, progress: `Failed to mine block, trying another...` });
        await exploreArea(10);
      }
    }

    if (collected > 0) {
      logMilestone(`Mined ${collected} ${blockName}`);
      completeTodo([blockName, blockName.replace('_ore', '')]);
      clearTask();
    } else {
      clearTask(`Could not mine any ${blockName}`);
    }
  } catch (err) {
    clearTask(err.message);
  }
}

// ─── AUTONOMOUS SELF-DRIVING PROGRESSION ENGINE ─────────────

async function autonomousProgressionStep() {
  if (isExecutingProgression || currentTask !== 'idle' || !bot.entity) return;
  isExecutingProgression = true;

  try {
    const logs = countItemInInventory('_log') + countItemInInventory('_wood') + countItemInInventory('stem');
    const planks = countItemInInventory('planks');
    const cobble = countItemInInventory('cobblestone') + countItemInInventory('stone') + countItemInInventory('deepslate') + countItemInInventory('cobbled_deepslate');
    const ironOre = countItemInInventory('raw_iron') + countItemInInventory('iron_ore');
    const ironIngots = countItemInInventory('iron_ingot');
    const coal = countItemInInventory('coal') + countItemInInventory('charcoal');
    const diamonds = countItemInInventory('diamond');
    const food = countItemInInventory('beef') + countItemInInventory('porkchop') + countItemInInventory('mutton') + countItemInInventory('chicken') + countItemInInventory('bread') + countItemInInventory('cooked');
    const rawFood = countItemInInventory('beef') + countItemInInventory('porkchop') + countItemInInventory('mutton') + countItemInInventory('chicken');
    const wool = countItemInInventory('wool');

    const hasAnyPickaxe = bot.inventory.items().some(i => i.name.includes('pickaxe'));
    const hasStonePickaxe = bot.inventory.items().some(i => i.name === 'stone_pickaxe' || i.name === 'iron_pickaxe' || i.name === 'diamond_pickaxe' || i.name === 'netherite_pickaxe');
    const hasIronPickaxe = bot.inventory.items().some(i => i.name === 'iron_pickaxe' || i.name === 'diamond_pickaxe' || i.name === 'netherite_pickaxe');

    // ─── 0. NIGHT SLEEPING ───
    if (bot.time && !bot.time.isDay) {
      const hasBed = bot.inventory.items().some(i => i.name.includes('_bed') || i.name === 'bed') || (wool >= 3 && planks >= 3);
      if (hasBed) {
        await handleSleep();
        return;
      }
    }

    // ─── 1. WOOD AGE (Gather logs & craft wooden pickaxe) ───
    if (!hasAnyPickaxe) {
      if (logs < 3 && planks < 6) {
        await handleMineBlock('log', 4);
        return;
      }
      await ensurePlanks(6);
      await ensureSticks(2);
      await handleCraft('wooden_pickaxe', 1);
      return;
    }

    // ─── 2. STONE AGE (Mine stone & craft stone gear + furnace) ───
    if (!hasStonePickaxe) {
      if (cobble < 12) {
        await handleMineBlock('stone', 10);
        return;
      }
      await ensurePlanks(4);
      await ensureSticks(2);
      await handleCraft('stone_pickaxe', 1);
      return;
    }

    // Craft stone sword for defense & hunting
    if (!bot.inventory.items().some(i => i.name === 'stone_sword' || i.name === 'iron_sword' || i.name === 'diamond_sword')) {
      if (cobble < 2) {
        await handleMineBlock('stone', 4);
        return;
      }
      await ensureSticks(1);
      await handleCraft('stone_sword', 1);
      return;
    }

    // Craft stone axe for fast wood chopping
    if (!bot.inventory.items().some(i => i.name === 'stone_axe' || i.name === 'iron_axe' || i.name === 'diamond_axe')) {
      if (cobble < 3) {
        await handleMineBlock('stone', 4);
        return;
      }
      await ensureSticks(2);
      await handleCraft('stone_axe', 1);
      return;
    }

    // Craft furnace
    if (!bot.inventory.items().some(i => i.name === 'furnace')) {
      if (cobble < 8) {
        await handleMineBlock('stone', 8);
        return;
      }
      await handleCraft('furnace', 1);
      return;
    }

    // ─── 3. FOOD & BED ───
    if (food < 3 || wool < 3) {
      await handleHuntAnimals(2);
      return;
    }

    if (rawFood > 0 && !bot.inventory.items().some(i => i.name.startsWith('cooked_'))) {
      const firstRaw = bot.inventory.items().find(i => i.name === 'beef' || i.name === 'porkchop' || i.name === 'mutton' || i.name === 'chicken');
      if (firstRaw) {
        await handleSmelt(firstRaw.name, 'coal', 2);
        return;
      }
    }

    if (!bot.inventory.items().some(i => i.name.includes('_bed') || i.name === 'bed')) {
      if (wool >= 3) {
        await ensurePlanks(3);
        await handleCraft('white_bed', 1);
        return;
      }
    }

    // ─── 4. COAL & IRON AGE ───
    if (coal < 4) {
      const coalBlock = findMineableBlock(getBlockMatcher('coal_ore'), 40);
      if (coalBlock) {
        await handleMineBlock('coal_ore', 4);
        return;
      }
    }

    if (ironOre > 0 && ironIngots < 5) {
      await handleSmelt('raw_iron', 'coal', Math.min(ironOre, 5));
      return;
    }

    if (ironIngots < 5 && ironOre === 0) {
      const ironBlock = findMineableBlock(getBlockMatcher('iron_ore'), 45);
      if (ironBlock) {
        await handleMineBlock('iron_ore', 4);
        return;
      }
    }

    // Craft Shield
    if (!bot.inventory.items().some(i => i.name === 'shield')) {
      if (ironIngots >= 1 && (planks >= 6 || logs >= 2)) {
        await ensurePlanks(6);
        await handleCraft('shield', 1);
        return;
      }
    }

    // Craft Iron Gear
    if (!hasIronPickaxe && ironIngots >= 3) {
      await ensureSticks(2);
      await handleCraft('iron_pickaxe', 1);
      return;
    }
    if (!bot.inventory.items().some(i => i.name === 'iron_sword') && ironIngots >= 2) {
      await ensureSticks(1);
      await handleCraft('iron_sword', 1);
      return;
    }
    if (!bot.inventory.items().some(i => i.name === 'iron_helmet') && ironIngots >= 5) {
      await handleCraft('iron_helmet', 1);
      return;
    }
    if (!bot.inventory.items().some(i => i.name === 'iron_chestplate') && ironIngots >= 8) {
      await handleCraft('iron_chestplate', 1);
      return;
    }
    if (!bot.inventory.items().some(i => i.name === 'iron_leggings') && ironIngots >= 7) {
      await handleCraft('iron_leggings', 1);
      return;
    }
    if (!bot.inventory.items().some(i => i.name === 'iron_boots') && ironIngots >= 4) {
      await handleCraft('iron_boots', 1);
      return;
    }

    // ─── 5. DIAMONDS & DEEP MINING ───
    if (diamonds === 0 && hasIronPickaxe) {
      const diamondBlock = findMineableBlock(getBlockMatcher('diamond_ore'), 48);
      if (diamondBlock) {
        await handleMineBlock('diamond_ore', 2);
        return;
      }
    }

    if (diamonds >= 3 && !bot.inventory.items().some(i => i.name === 'diamond_pickaxe')) {
      await ensureSticks(2);
      await handleCraft('diamond_pickaxe', 1);
      return;
    }
    if (diamonds >= 2 && !bot.inventory.items().some(i => i.name === 'diamond_sword')) {
      await ensureSticks(1);
      await handleCraft('diamond_sword', 1);
      return;
    }

    // Torches
    if (coal > 0 && countItemInInventory('torch') < 8) {
      await ensureSticks(1);
      await handleCraft('torch', 4);
      return;
    }

    // ─── 6. IDLE ROAM & EXPLORE ───
    await exploreArea(25);
  } catch (e) {
    send({ type: 'error', msg: `[Progression Error] ${e.message}` });
    currentTask = 'idle';
  } finally {
    isExecutingProgression = false;
  }
}

// ─── ACTIVE ANTI-AFK & WATCHDOG TIMER ───────────────────────

setInterval(() => {
  if (!bot.entity) return;
  if (currentTask === 'idle') {
    const newYaw = bot.entity.yaw + (Math.random() - 0.5) * 1.5;
    const newPitch = (Math.random() - 0.5) * 0.6;
    bot.look(newYaw, newPitch, true).catch(() => {});

    if (Math.random() < 0.4) {
      bot.swingArm('right');
    }
    if (Math.random() < 0.25) {
      bot.setControlState('sneak', true);
      setTimeout(() => {
        try { bot.setControlState('sneak', false); } catch(e) {}
      }, 350);
    }
  }
}, 4000);

// Dynamic Task watchdog (aborts truly stuck tasks after 35s)
setInterval(() => {
  if (currentTask !== 'idle' && Date.now() - currentTaskStartTime > 35000) {
    send({ type: 'task_failed', task: currentTask, reason: 'Task reset after 35s safety watchdog timeout.' });
    try { bot.pathfinder.stop(); } catch(e) {}
    try { bot.pvp.stop(); } catch(e) {}
    currentTask = 'idle';
    currentTaskStartTime = Date.now();
    isExecutingProgression = false;
  }
}, 5000);

// Autonomous progression pulse (runs every 3.5s whenever idle)
setInterval(() => {
  if (!autonomousEnabled) return;
  const idleDuration = Date.now() - lastUserActivityTime;
  if (idleDuration > 1500 && currentTask === 'idle' && !isExecutingProgression) {
    autonomousProgressionStep().catch(() => {});
  }
}, 3500);

// Safety release for stuck progression flag
setInterval(() => {
  if (currentTask === 'idle' && isExecutingProgression) {
    isExecutingProgression = false;
  }
}, 5000);

// ─── IPC COMMAND PROCESSOR ──────────────────────────────────

rl.on('line', async (line) => {
  try {
    const cmd = JSON.parse(line.trim());
    const type = cmd.type;
    lastUserActivityTime = Date.now();

    if (type === 'chat') {
      bot.chat(cmd.text || '');
    } else if (type === 'whisper') {
      bot.whisper(cmd.user, cmd.text || '');
    } else if (type === 'goto') {
      const { x, y, z, range = 1 } = cmd;
      setTask(`walking to ${x}, ${y}, ${z}`);
      bot.pathfinder.setGoal(new goals.GoalNear(x, y, z, range));
    } else if (type === 'follow') {
      let target = null;
      for (const p in bot.players) {
        if (p.toLowerCase() === (cmd.username || '').toLowerCase()) {
          target = bot.players[p];
          break;
        }
      }
      if (target && target.entity) {
        setTask(`following ${target.username}`);
        followingTarget = target.entity;
        bot.pathfinder.setGoal(new goals.GoalFollow(target.entity, cmd.range || 2), true);
      } else {
        clearTask('Player not in render distance');
      }
    } else if (type === 'stop') {
      try { bot.pathfinder.stop(); } catch (e) {}
      try { bot.pvp.stop(); } catch (e) {}
      currentTask = 'idle';
      guardPos = null;
      followingTarget = null;
      isExecutingProgression = false;
      send({ type: 'task_stopped' });
    } else if (type === 'mine') {
      handleMineBlock(cmd.block, cmd.count || 1);
    } else if (type === 'craft') {
      handleCraft(cmd.item, cmd.count || 1);
    } else if (type === 'smelt') {
      handleSmelt(cmd.item, cmd.fuel || 'coal', cmd.count || 1);
    } else if (type === 'hunt') {
      handleHuntAnimals(cmd.count || 2);
    } else if (type === 'sleep') {
      handleSleep();
    } else if (type === 'wake') {
      bot.wake().catch(() => {});
    } else if (type === 'give') {
      handleGive(cmd.username, cmd.item, cmd.count || 1);
    } else if (type === 'toss') {
      const item = bot.inventory.items().find(i => i.name.includes(cmd.item));
      if (item) bot.toss(item.type, null, cmd.count || 1).catch(() => {});
    } else if (type === 'attack' || type === 'pvp') {
      await equipBestWeapon();
      await equipShield();
      const targetQuery = (cmd.target || '').toLowerCase();
      const ent = bot.nearestEntity(e => {
        if (!targetQuery) return (e.type === 'mob' || e.type === 'hostile' || e.type === 'player') && e !== bot.entity;
        return (e.name && e.name.toLowerCase().includes(targetQuery)) || (e.username && e.username.toLowerCase().includes(targetQuery));
      });
      if (ent) {
        setTask(`pvp attacking ${ent.username || ent.name}`);
        bot.pvp.attack(ent);
      } else {
        clearTask(`Target '${cmd.target || 'hostile'}' not found nearby.`);
      }
    } else if (type === 'guard') {
      guardPos = bot.entity.position.clone();
      setTask('guard');
      await equipBestWeapon();
      await equipShield();
    } else if (type === 'emote') {
      const emoteType = cmd.emote || 'sneak_spam';
      if (emoteType === 'sneak_spam') performSneakSpam(cmd.count || 3);
      else if (emoteType === 'nod') performNod(cmd.count || 2);
      else if (emoteType === 'shake') performShakeHead(cmd.count || 2);
      else if (emoteType === 'jump') performJump();
    } else if (type === 'journal') {
      send({ type: 'journal_data', journal });
    } else if (type === 'inventory') {
      send({ type: 'inventory_data', items: getInventoryList() });
    } else if (type === 'status') {
      send({
        type: 'status',
        health: bot.health,
        food: bot.food,
        pos: {
          x: Math.round(bot.entity.position.x),
          y: Math.round(bot.entity.position.y),
          z: Math.round(bot.entity.position.z)
        },
        task: currentTask,
        players: getNearbyPlayers(),
        mobs: getNearbyMobs(),
        inventory: getInventoryList(),
        journal
      });
    } else if (type === 'quit') {
      bot.quit();
      process.exit(0);
    }
  } catch (e) {
    send({ type: 'error', msg: e.message });
  }
});

// Periodic telemetry status stream (every 5 seconds)
setInterval(() => {
  if (!bot.entity) return;
  send({
    type: 'status',
    health: bot.health,
    food: bot.food,
    pos: {
      x: Math.round(bot.entity.position.x),
      y: Math.round(bot.entity.position.y),
      z: Math.round(bot.entity.position.z)
    },
    task: currentTask,
    players: getNearbyPlayers(),
    mobs: getNearbyMobs(),
    journal
  });
}, 5000);
