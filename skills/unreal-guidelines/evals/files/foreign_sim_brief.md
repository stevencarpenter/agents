# Brief: gameplay subsystem for a foreign simulation

The terrain simulation is a Rust `staticlib`. Its C header `snow_sim.h` exposes:

```c
typedef struct SnowSim SnowSim;
SnowSim* snow_sim_create(uint32_t width, uint32_t height, int32_t* out_status);
void     snow_sim_destroy(SnowSim* sim);
int32_t  snow_sim_step(SnowSim* sim, double dt_seconds);            // not thread safe
int32_t  snow_sim_add_impulse(SnowSim* sim, double x_cm, double y_cm, double force_n);
int32_t  snow_sim_read_heights(const SnowSim* sim, float* out, size_t count); // copies a snapshot
const char* snow_sim_last_error(const SnowSim* sim);
```

Requirements:

1. Sleds (physics actors) push snow. Each physics step, every sled sends an impulse at its location. Sled forces are authored in newtons.
2. The simulation steps at a fixed 1/60 s. The project uses `bTickPhysicsAsync`, so the step must stay in sync with the physics thread step.
3. The renderer reads a height snapshot each frame to drive a displaced plane.
4. One owner for the `SnowSim*` handle. The handle must be freed exactly once, including on PIE stop and level travel.
5. The Rust code must never panic across the boundary. Failures come back as status codes.
6. The game runs standalone on macOS. Multiplayer is out of scope, but name the authority rule you would use if it came later.

Deliver a design: the class list with UE base classes, who owns the handle, threading and locking, how impulses and snapshots move between threads, the unit conversion point, and the lifecycle calls. Include a header sketch for the subsystem and a test plan.
