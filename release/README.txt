Okami HD High-FPS Patch 1.0.0
=============================

Runs the Steam version of Okami HD at 60 or 120 fps instead of its fixed
30, with the game's speed kept right: Amaterasu runs, jumps and fights at
the same pace as at 30 fps, and timers, effects, menus and animations last
as long as they do at 30.

Made for the Steam release of Okami HD (build 6990973). The patch checks
the game's code before it changes anything. On a version it does not
recognise, it leaves the game as shipped and says so on screen.


Install
-------

1. Find the game folder: in Steam, right-click Okami HD, then Manage >
   Browse local files. It is the folder with okami.exe in it.
2. Copy DINPUT8.dll into that folder.
3. Start the game. A short notice at the top left shows the frame rate.

okami_hackfix.ini is optional. Copy it in as well if you want to change a
setting; the patch works the same without it.


In game
-------

F9 cycles the frame rate: 30 -> 60 -> 120 -> 30. A notice shows the new
rate for a moment. The game starts at the rate you last picked; the patch
saves it in okami_hackfix.ini, which it creates in the game folder if it is
not there.

30 fps is the game as shipped.

Pick a rate your PC can hold steadily. The game advances one step per frame,
so if it drops below the rate you picked, the whole game runs in slow
motion (at 120, 90 fps is 75% speed). If that happens, press F9 to go down
a step.

- Turn off frame generation (for example NVIDIA Smooth Motion) and any frame
  limiter set below the rate you picked. Either one slows the game down.
- A G-Sync / FreeSync / VRR display gives the smoothest result. 120 fps
  needs a display that refreshes at 120 Hz or more to look smooth.
- 120 is only offered when the game's code matches what the patch expects.
  Otherwise F9 switches between 30 and 60.


Settings (okami_hackfix.ini)
----------------------------

The file in this zip lists the settings, with their defaults:

  DefaultFps     the rate the game starts at: 30, 60 or 120 (F9 updates it)
  ToggleKey      the key that cycles the rate (F9; None turns it off)
  RequireFocus   the key only works while the game window is in front
  Beep           a system beep when the rate changes
  SyncInterval   0 = the patch paces frames (best with VRR); 1 = wait for
                 the display's refresh, for a fixed-rate display in a window
  DrawDistance   1 = as shipped; 2 to 6 = draw scenery and objects that many
                 times farther (costs frame time)
  ProxyDll       another mod's DINPUT8.dll to load as well (see below)


Other mods
----------

ReShade (and its add-ons) and the Steam overlay work alongside the
patch.

If another mod also comes as a DINPUT8.dll, rename that mod's file (for
example to dinput8_other.dll), put both files in the game folder, and set
ProxyDll=dinput8_other.dll in okami_hackfix.ini.


Steam Deck and Linux (Proton)
-----------------------------

Not tested. Proton loads its own dinput8 unless told otherwise, so set the
game's launch options in Steam to:

  WINEDLLOVERRIDES="dinput8=n,b" %command%


Uninstall
---------

Delete DINPUT8.dll from the game folder, and okami_hackfix.ini and
okami_hackfix.log if they are there. The patch changes nothing on disk, so
nothing else needs undoing, and Steam's "Verify integrity of game files"
has nothing to repair.


If something looks wrong
------------------------

- A red notice at start-up means part of the patch did not go in, or the
  game version was not recognised. The game still runs. If the version was
  not recognised, it runs as shipped at 30. If part did not go in, that part
  may run too fast at 60 or 120; 30 is unaffected.
- Something animating too fast or too slow at 60 or 120: press F9 until it
  reads 30 to compare with the game as shipped. A few animations may still
  run at the wrong speed; reports help.
- With a report, include okami_hackfix.log from the game folder. It records
  what the patch found and changed at start-up.


License
-------

MIT; see LICENSE.txt.
