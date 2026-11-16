# v012 test guide (AI line + TV cameras)

Tracks: **Exelberg Full v012** and **Exelberg Reverse v012**. Road, scenery and timing are the same as v011.

1. **Load:** solo Practice. If the track fails to load, check `Documents/Assetto Corsa/logs/log.txt` in the Proton prefix
   (compatdata/244210) for `fast_lane.ai` or camera errors.
2. **Track position:** drive a little way. Content Manager's track map / the in-game progress should move smoothly
   from the start (AI line starts 10 m behind the spawn).
3. **TV cameras:** drive (or replay) a run, press **F3** for track cameras, press F3 again to cycle sets:
   - TV 1 broadcast (eye-level, zooms), TV 2 low trackside, TV 3 high.
   - Check that the view cuts to the next camera before the car disappears behind trees or a hill. Note the km or the
     place if a camera mostly shows trees.
4. **AI cars:** not testable yet. The tracks have one pit box / grid slot, so AC cannot add AI opponents. The AI line is
   used for track position and camera switching; AI driving would need more pit boxes and starting spots (later version).
