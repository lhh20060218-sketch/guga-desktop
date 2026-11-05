"""Bounded static audit of installed assemblies; never loads or invokes game code.

Mono.Cecil reads metadata/IL as data. No process attachment, privilege changes,
input, memory writes, HTTP requests or API credentials are used by this tool.
"""
import argparse
import hashlib
import json
from pathlib import Path


CALL_OPS = frozenset(('call', 'callvirt', 'newobj'))
ACTION_NAMES = frozenset(('SendOption', 'SetSelectedOption', 'SetSelectedSubOption',
                          'SetSelectedOptionTarget', 'SetSelectedOptionPosition',
                          'GetOptionsPacket'))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def all_types(module):
    """Include nested types: omitting them loses coroutine/callback evidence."""
    def walk(types):
        for item in types:
            yield item
            yield from walk(item.NestedTypes)
    yield from walk(module.Types)


def calls(method):
    if not method.HasBody:
        return []
    return [str(ins.Operand) for ins in method.Body.Instructions
            if str(ins.OpCode) in CALL_OPS]


def method_record(method):
    return dict(signature=str(method.FullName), static=bool(method.IsStatic),
                public=bool(method.IsPublic), has_body=bool(method.HasBody),
                calls=calls(method))


def check_saved_identity(evidence, actual_digest):
    saved = evidence.get('assembly_sha256')
    return dict(recorded=saved, actual=actual_digest,
                matches=bool(saved) and saved == actual_digest,
                meaning='Hash equality binds static evidence, not runtime compatibility')


def audit(game_path, mirror_path, cecil_path, evidence_path):
    import clr
    # Only the metadata parser is loaded. Do not AddReference either target.
    clr.AddReference(str(Path(cecil_path).resolve()))
    from Mono.Cecil import AssemblyDefinition
    game_hash = sha256(game_path)
    game = AssemblyDefinition.ReadAssembly(str(Path(game_path).resolve()))
    mirror = AssemblyDefinition.ReadAssembly(str(Path(mirror_path).resolve()))
    saved = json.loads(Path(evidence_path).read_text(encoding='utf-8-sig'))
    game_types = list(all_types(game.MainModule))
    mirror_types = list(all_types(mirror.MainModule))
    action_methods = [method_record(m) for t in game_types
                      if str(t.FullName) in ('GameState', 'Network')
                      for m in t.Methods if str(m.Name) in ACTION_NAMES]
    direct_callers = []
    for t in game_types:
        for m in t.Methods:
            hits = [c for c in calls(m) if 'GameState::SendOption(' in c]
            if hits:
                direct_callers.append(dict(caller=str(m.FullName), calls=hits))
    interfaces = [dict(type=str(t.FullName),
                       methods=[str(m.FullName) for m in t.Methods])
                  for t in mirror_types if str(t.FullName) == 'HearthMirror.IReflection']
    mirror_runtime = [method_record(m) for t in mirror_types
                      if str(t.FullName) in ('HearthMirror.IpcClient', 'HearthMirror.Reflection')
                      for m in t.Methods
                      if str(m.Name) in ('get_Client', '.cctor', 'MaintenanceThread', 'GetBoardState')]
    dispatcher = [dict(type=str(t.FullName), methods=[str(m.FullName) for m in t.Methods])
                  for t in game_types if str(t.FullName) == 'Networking.QueueDispatcher']
    return dict(
        source='Local Mono.Cecil metadata/IL audit; no runtime target execution',
        target_identity=check_saved_identity(saved, game_hash),
        mirror_sha256=sha256(mirror_path),
        game_assembly=str(game.Name), mirror_assembly=str(mirror.Name),
        action_methods=action_methods, direct_send_option_callers=direct_callers,
        mirror_interfaces=interfaces, mirror_runtime_candidates=mirror_runtime,
        queue_dispatcher=dispatcher,
        findings=dict(
            game_has_internal_action_methods=bool(action_methods),
            mirror_interface_action_methods=[s for item in interfaces for s in item['methods']
                if any('::'+n+'(' in s for n in ('SendOption','WriteProcessMemory','Execute','Invoke'))],
            runtime_thread_context_verified=False, external_game_bridge_verified=False,
            transport_ready=False, input_sent=False, memory_written=False,
            note='Dispatcher names and internal call sites do not establish a usable external bridge'),
        limitations=['Static metadata does not establish live object addresses or thread affinity',
                     'IpcClient proxies a helper reader; its IPC is not evidence of game action RPC',
                     'No process permission probe is performed; prior AccessDenied remains historical'])


def main():
    root = Path(__file__).resolve().parents[1]
    hdt = Path.home() / 'Desktop/游戏/HDT'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembly', type=Path, required=True)
    parser.add_argument('--mirror', type=Path, default=hdt/'HearthMirror.dll')
    parser.add_argument('--cecil', type=Path, default=hdt/'Mono.Cecil.dll')
    parser.add_argument('--evidence', type=Path,
                        default=root/'runtime/bg-client-action-evidence-20261023.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.assembly, args.mirror, args.cecil, args.evidence)
    if args.output:
        # Explicit output only; do not modify a pre-existing artifact.
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps(dict(identity=result['target_identity'], findings=result['findings'],
                          callers=len(result['direct_send_option_callers']),
                          mirror_methods=sum(len(t['methods']) for t in result['mirror_interfaces'])),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
