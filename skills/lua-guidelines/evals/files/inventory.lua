-- inventory.lua: player inventory for the game scripting layer (Lua 5.4)

inventory = {}
items = {}

function add_item(name, count)
  if items[name] == nil then
    items[#items + 1] = name
  end
  items[name] = (items[name] or 0) + count
end

function remove_item(name)
  items[name] = nil
  -- keep the list in sync
  for i = 1, #items do
    if items[i] == name then
      items[i] = nil
    end
  end
end

function item_count()
  return #items
end

function load_save(path)
  local f = io.open(path, "r")
  local data = f:read("*a")
  local ok, chunk = pcall(load, data)
  local ok2, result = pcall(chunk)
  return result
end

function use_item(name, player)
  local ok, err = pcall(function()
    if items[name] == nil then
      error("no such item: " .. name)
    end
    player.hp = player.hp + items[name].heal
  end)
end

function describe_all()
  local s = ""
  for k, v in pairs(items) do
    s = s .. k .. "=" .. tostring(v) .. ";"
  end
  return s
end

function ratio(a, b)
  return a / b == 0.5
end
