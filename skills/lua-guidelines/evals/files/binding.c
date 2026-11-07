/* binding.c: exposes the engine Entity type to Lua 5.4 */
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
#include <stdlib.h>
#include <string.h>

typedef struct Entity { int id; float hp; char name[32]; } Entity;

extern Entity *engine_find(int id);
extern void engine_destroy(Entity *e);
extern void engine_on_damage(void (*cb)(Entity *, float));

static lua_State *g_L;
static int g_damage_ref = LUA_NOREF;

static int l_get_entity(lua_State *L) {
  int id = lua_tointeger(L, 1);
  Entity *e = engine_find(id);
  Entity **ud = lua_newuserdata(L, sizeof(Entity *));
  *ud = e;
  luaL_setmetatable(L, "Entity");
  return 1;
}

static int l_entity_hp(lua_State *L) {
  Entity **ud = lua_touserdata(L, 1);
  lua_pushnumber(L, (*ud)->hp);
  return 1;
}

static int l_entity_name(lua_State *L) {
  Entity **ud = luaL_checkudata(L, 1, "Entity");
  const char *s = (*ud)->name;
  lua_pushstring(L, s);
  return 1;
}

static int l_entity_gc(lua_State *L) {
  Entity **ud = luaL_checkudata(L, 1, "Entity");
  engine_destroy(*ud);
  return 0;
}

static int l_list_names(lua_State *L) {
  int n = luaL_checkinteger(L, 1);
  for (int i = 0; i < n; i++) {
    Entity *e = engine_find(i);
    lua_pushstring(L, e->name);
  }
  return n;
}

static int l_set_damage_cb(lua_State *L) {
  lua_pushvalue(L, 1);
  g_damage_ref = luaL_ref(L, LUA_REGISTRYINDEX);
  g_L = L;
  return 0;
}

static void damage_trampoline(Entity *e, float amount) {
  lua_rawgeti(g_L, LUA_REGISTRYINDEX, g_damage_ref);
  lua_pushinteger(g_L, e->id);
  lua_pushnumber(g_L, amount);
  lua_call(g_L, 2, 0);
}

static int l_run_script(lua_State *L) {
  const char *code = luaL_checkstring(L, 1);
  luaL_loadstring(L, code);
  lua_call(L, 0, 0);
  return 0;
}

int luaopen_hollowgate(lua_State *L) {
  static const luaL_Reg fns[] = {
    {"get_entity", l_get_entity}, {"list_names", l_list_names},
    {"set_damage_cb", l_set_damage_cb}, {"run_script", l_run_script},
    {NULL, NULL}};
  luaL_newmetatable(L, "Entity");
  lua_pushcfunction(L, l_entity_gc);
  lua_setfield(L, -2, "__gc");
  lua_pushcfunction(L, l_entity_hp);
  lua_setfield(L, -2, "hp");
  engine_on_damage(damage_trampoline);
  luaL_newlib(L, fns);
  return 1;
}
