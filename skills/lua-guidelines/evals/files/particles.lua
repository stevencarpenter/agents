-- particles.lua: per-frame particle update, runs 60 times per second on LuaJIT 2.1
local M = {}

function M.update(particles, dt)
  local alive = {}
  for i, p in ipairs(particles) do
    local pos = { x = p.x + p.vx * dt, y = p.y + p.vy * dt }
    local life = p.life - dt
    if life > 0 then
      alive[#alive + 1] = { x = pos.x, y = pos.y, vx = p.vx, vy = p.vy, life = life }
    end
  end
  return alive
end

function M.label(particles)
  local out = ""
  for i = 1, #particles do
    out = out .. string.format("%d:%.2f,%.2f;", i, particles[i].x, particles[i].y)
  end
  return out
end

function M.nearest(particles, x, y)
  local best, best_d
  for _, p in pairs(particles) do
    local d = math.sqrt((p.x - x) ^ 2 + (p.y - y) ^ 2)
    if not best_d or d < best_d then
      best, best_d = p, d
    end
  end
  return best
end

function M.render(particles, draw)
  for _, p in ipairs(particles) do
    draw(math.floor(p.x), math.floor(p.y), string.format("p%d", math.floor(p.life * 10)))
  end
end

return M
