# `@actplane/dsh-feedback`

This is the ActPlane integration bundle for DeepSeek Harness (DSH). It runs
`actplane feedback-hook` after each DSH tool execution and forwards a newly
matched policy violation as `additionalContext` to the next agent turn.

The package is a normal DSH bundle: its `package.json` declares
`dsh.bundle.patch`, and its patch registers the native plugin. It should be
installed through the DSH profile manager so the profile records both the
dependency and the ordered bundle entry.

The bundle declares the DSH LLM and schema API versions it needs as peer
dependencies. The provided installer resolves those peers when adding the
bundle to a profile. Its JavaScript entrypoint is shipped directly, so
installation does not need a local build step.

## Install from this checkout

From the ActPlane checkout, run:

```bash
dsh plugin --profile web add --config.auto-install-peers=true file:./integrations/dsh-feedback
```

Then verify the registered profile:

```bash
dsh plugin --profile web list --depth 0
dsh --profile web --dump-config | grep -A5 -B2 actplane-feedback-native
```

Restart `dsh web` after installation. Do not copy the package into
`~/.dsh/profiles/node_modules` or add it to `cordis.patch.yml` by hand; those
paths bypass the profile's dependency and bundle registry.

The default binary is `/usr/local/bin/actplane`. Override it in the profile
patch when ActPlane is installed elsewhere:

```yaml
- id: actplane-feedback-native
  config:
    binary: /path/to/actplane
    timeoutMs: 5000
```

The DSH plugin is only a feedback transport. ActPlane's kernel runtime remains
the authority for observation and enforcement.
