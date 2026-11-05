# Third-party and asset notices

- Python packages retain their own licenses; see `requirements.txt` and the packages installed by pip.
- PyQt5/Qt follows the upstream Qt and PyQt licensing terms.
- `lib/HearthDb.dll` and Hearthstone card data are used for local card/metadata compatibility. Hearthstone and related card data are trademarks or copyrighted works of Blizzard Entertainment; this project is not affiliated with Blizzard.
- `lib/HearthMirror.dll` and `lib/untapped-scry-dotnet.dll` are third-party read-only libraries used to parse the local game log/memory for the battlegrounds advisor feature. They remain under their respective upstream licenses and are not affiliated with Blizzard Entertainment.
- `lib/Newtonsoft.Json.dll` is a runtime dependency of the libraries above and keeps its upstream license.
- The optional speaker-recognition ONNX model is downloaded separately and is excluded from this repository. Check the upstream sherpa-onnx/3D-Speaker model terms before redistribution.
- The character artwork, Blender model and animation frames were supplied or generated for this project. They are included so the desktop pet can run; the MIT code license does not independently grant rights to third-party or source material embedded in those assets.

If you redistribute the project, review these notices and the applicable upstream terms.
