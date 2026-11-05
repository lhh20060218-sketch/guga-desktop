# 本地声纹模型

运行时通过 `python tools/download_speaker_model.py` 下载：

`3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx`

来源：[sherpa-onnx speaker recognition models](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models)，上游为 3D-Speaker 中文说话人确认模型。模型文件被 `.gitignore` 排除；分发或再训练前需核对上游模型许可证与引用要求。

声纹只用于本地主人/非主人门禁，不用于声纹解锁之外的账号认证。
