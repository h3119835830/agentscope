"""Git policy contracts. Unsupported semantics never produce an executable DSL."""
import copy

RETIRED = {'RQ1-GIT': ['GIT-COMMIT', 'GIT-PUSH', 'GIT-LOCAL', 'GIT-BYPASS'],
           'RQ1-CHECK': ['GIT-COMMIT-CHECK', 'GIT-PUSH-CHECK']}


def definitions(template, field):
    program = field('program', 'Git 可执行程序名或路径', 'git', 'program',
                    help='按程序及参数字面值匹配，不解析 Git 别名；不按当前目录区分仓库。')
    effect = field('effect', '匹配后的动作', 'kill', 'effect')
    common = ['参数在 exec 后观察：记录或终止命中进程，不能保证副作用发生前已阻断。',
              '仅匹配前 128 字节、最多 16 个参数槽中的字面 token；不解析子命令位置、别名或 Git 配置。',
              '作用于所选 Agent 的共享执行域；不按仓库或会话隔离。']
    result = []

    def add(ident, name, summary, renderer, parameters, *, event='单事件', supported=(), unsupported=(), applicable=True, **extra):
        note = ' '.join(common) if applicable else 'ActPlane 当前暂不支持此语义；只能保存参数草案，不能提交审批或应用。'
        item = template(ident, name, 'Git 操作', summary, renderer, copy.deepcopy(parameters),
                        effect='kill' if applicable else 'block', operation='exec', note=note)
        item.update(extra)
        item['allowed_effects'] = ['notify', 'kill'] if applicable else ['block']
        item['execution_support'] = {'status': 'limited' if applicable else 'unsupported', 'applicable': applicable,
            'event_type': event, 'supported': list(supported), 'unsupported': list(unsupported),
            'boundary': common if applicable else ['参数草案不生成 DSL；服务端拒绝单项、批量审批及重新校验应用。']}
        result.append(item)

    for command, label in [('commit', '提交'), ('push', '推送')]:
        add('GIT-' + command.upper(), 'Git ' + label + '执行约束',
            '对 Git ' + command + ' 参数命中事件记录或终止命中进程。适用于限制所选 Agent 的全部' + label + '执行，不限定仓库或分支。',
            'git-command', [program, effect], command=command,
            supported=['将 Git 程序和 ' + command + ' 参数写入实际 DSL。', '动作可选记录并提醒或终止命中进程。'],
            unsupported=['按仓库、远端、分支或提交内容选择性放行。', '执行前按参数阻断。'])
        add('GIT-' + command.upper() + '-CHECK', 'Git ' + label + '前检查事件',
            '在 Git ' + command + ' 参数命中前要求已观测到指定检查程序以指定退出码结束；目标代码再次写入后检查失效。此模板不证明待' + label + '内容测试通过。',
            'git-check', [program, field('target', '使检查失效的代码路径', kind='path', help='此路径是检查失效条件，不是 Git 仓库匹配条件。'),
                          field('checker', '检查程序名或路径', kind='program', help='仅匹配程序，不校验脚本参数、测试用例或可信 CI 身份。'),
                          field('exit_code', '检查成功退出码', '0', 'integer', minimum=0, maximum=255), effect],
            command=command, event='跨事件',
            supported=['检查程序退出码和代码写入后的失效条件实际写入 DSL。', '缺少有效检查事件时记录或终止命中进程。'],
            unsupported=['检查结果与暂存区、待推送提交 SHA 的一致性。', '指定测试命令参数、可信 CI 结果或多会话独立检查。', '执行前按参数阻断。'])

    add('GIT-LOCAL', 'Git 本地历史与清理约束',
        '按所选 reset、clean、stash 字面参数记录或终止进程。选择 reset 会影响全部 reset，不仅是 --hard；路径和选项组合过滤暂不支持。',
        'git-tokens', [program, field('tokens', '需要约束的 Git 操作', 'reset,clean,stash', 'choices',
            options=['reset', 'clean', 'stash']), effect],
        supported=['每个所选参数分别生成匹配规则。'],
        unsupported=['只限制 reset --hard、clean -fd 或 stash drop 等组合。', '仅约束某个仓库或文件范围。'])
    add('GIT-BYPASS', 'Git 跳过检查参数约束',
        '对 --no-verify 等显式跳过检查的 Git 参数记录或终止进程。短参数 -n 在不同子命令中含义不同，不能将其统一认定为绕过检查。',
        'git-tokens', [program, field('tokens', '需要匹配的参数', '--no-verify', 'choices', options=['--no-verify']), effect],
        supported=['匹配显式 --no-verify 参数。'],
        unsupported=['识别 -n 的子命令语义、hooksPath 配置、环境变量或直接使用 Git 底层命令的绕过。'])
    repo = field('repository', '目标仓库路径', kind='path')
    add('GIT-CONTENT', 'Git 提交内容限制',
        '限制提交对象包含的敏感文件。需要读取暂存区与提交对象，不能用禁止打开文件代替内容检查；目前仅能保存需求参数。',
        'unsupported', [repo, field('forbidden_paths', '禁止提交的文件模式（每行一个）', kind='lines')],
        applicable=False, unsupported=['读取和验证待提交对象、暂存区文件清单。', '按提交内容执行事前拒绝。'])
    add('GIT-PUSH-TARGET', 'Git 推送目标限制',
        '限制推送的远端、目标分支及强推或删除行为。需要解析 Git 实际目标和引用更新，普通参数或网络地址匹配不能替代，目前仅能保存需求参数。',
        'unsupported', [repo, field('remote', '允许的远端仓库地址'), field('branches', '允许的目标分支（每行一个）', kind='lines'),
                        field('forbidden_updates', '禁止的引用更新', 'force,delete', 'choices', options=['force', 'delete'])],
        applicable=False, unsupported=['解析实际远端 URL、refspec、默认推送配置与分支。', '区分正常更新、强推及引用删除并选择性阻止。'])
    add('GIT-PUSH-APPROVAL', 'Git 单次推送授权',
        '要求本次提交向指定远端和分支推送前获得行为授权。此授权与策略配置审批不同；当前没有绑定推送内容的一次性授权机制。',
        'unsupported', [repo, field('commit', '本次推送的提交 SHA'), field('remote', '目标远端仓库地址'),
                        field('branch', '目标分支'), field('ttl_seconds', '授权有效秒数', '600', 'integer', minimum=1, maximum=86400)],
        event='跨事件', applicable=False, unsupported=['对提交、远端、分支绑定的一次性行为授权及消费。', '授权到期、代码变化后的自动失效。'])
    add('GIT-MERGE-GATE', 'Git 保护分支合并检查',
        '合入保护分支前必须取得指定来源的 CI 检查与评审。需要托管平台的权威检查和审批结果，目前没有 GitHub 或 GitLab 执行集成。',
        'unsupported', [repo, field('branches', '受保护分支（每行一个）', kind='lines'),
                        field('checks', '必需的 CI 检查（每行一个）', kind='lines'), field('issuer', '可信检查来源'),
                        field('reviewers', '最低批准人数', '1', 'integer', minimum=1, maximum=10)],
        event='跨事件', applicable=False, unsupported=['验证指定提交的可信 CI 与 Code Owner 或评审结果。', '调用托管平台保护分支规则或阻止远端合并。'])
    return result


def presentation(definition):
    """Add current capability facts without rewriting historical template hashes."""
    if 'execution_support' in definition:
        return copy.deepcopy(definition['execution_support'])
    if definition['id'] in RETIRED:
        return {'status': 'legacy', 'applicable': True, 'event_type': '跨事件' if definition['id']=='RQ1-CHECK' else '单事件',
                'supported': ['保留原模板版本、既有参数和 DSL，不迁移已有配置。'],
                'unsupported': ['已由专用 Git 模板替代；旧模板不提供新的细分参数。'],
                'boundary': [definition['note']]}
    return None


def validate_parameter(parameter, value):
    kind = parameter['type']
    if kind == 'choices':
        values = value.split(',') if isinstance(value, str) else value
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or v not in parameter['options'] for v in values) or len(set(values)) != len(values):
            raise ValueError('请选择模板支持的' + parameter['label'])
        return sorted(values)
    if kind == 'integer':
        if isinstance(value, str) and value.isascii() and value.isdigit():
            value = int(value)
        if type(value) is not int or not parameter['minimum'] <= value <= parameter['maximum']:
            raise ValueError(parameter['label'] + '须为 ' + str(parameter['minimum']) + ' 至 ' + str(parameter['maximum']) + ' 的整数')
        return value
    raise ValueError('参数类型不支持')


def ensure_applicable(definition):
    if not definition.get('execution_support', {}).get('applicable', True):
        raise ValueError('ActPlane 暂不支持“' + definition['name'] + '”的执行语义；参数草案已保留，不能提交审批或应用。')
