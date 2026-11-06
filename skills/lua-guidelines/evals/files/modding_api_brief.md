# Brief: `mod` scripting API for the Hollowgate engine

Design the Lua-facing API that community mods use. The engine is C++ and embeds Lua 5.4 on macOS and Linux. A LuaJIT build is planned for a low-end target.

## Requirements

- Mods register content: items, enemies, and recipes, as data-definition tables.
- Mods subscribe to events: `on_spawn`, `on_damage`, `on_tick` (60 times per second).
- Mods read and change entity state (health, position, tags) through handles, not raw pointers.
- Mods are untrusted. They must not touch the file system, network, or process, and a bad mod must not hang the game.
- Mods can be reloaded without restarting the game.
- Mods declare an API version. We expect to add fields and events over time, and to rename one event, without breaking existing mods.
- Mods may depend on other mods and must load in dependency order.

## Known consumer

```lua
local mod = require("hollowgate")
mod.items.define{ id = "ember_blade", damage = 12, tags = { "fire" } }
mod.events.on("on_damage", function(ev) ... end)
```

Deliverable: `outputs/mod_api.lua` (module skeleton with the public functions, validation, and doc comments; internals may be stubs) and `outputs/api_notes.md` explaining the shape, the sandbox and limits story, the reload story, and the versioning story.
