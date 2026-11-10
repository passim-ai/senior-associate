# Permission prompts during a build — November 10, 2026

What a build asks of an attorney in Claude's usual permission setting, what was tried, and why the app now recommends Auto. Everything used the fictional sample matter.

## Measured

One full build of the sample on the released 1.4.0 (desktop engine 2.1.321, permission mode `manual`, every prompt answered Allow by a stand-in and logged): **479 prompts in 74 minutes**, never more than 90 seconds apart, median gap 5 seconds.

| Kind | Prompts |
|---|---|
| Shell commands (326 of them compound) | 331 |
| Files written or edited in the matter folder | 53 |
| BIA Edge calls (14 distinct tools) | 50 |
| Web pages | 24 |
| Reads of the plugin's own files | 21 |

The build finished all 10 steps (19 agents, 895 tool calls, 124.8 million tokens, $34.89 at API prices).

## "Don't ask again" does not fix it

With allow rules in place for every program the build uses, a probe still raised a prompt for a command that uses a shell variable (`M="..."; cat "$M/x"`), a `for` loop, or a file written with `>`. Pipes and inline Python passed. About 272 of the 331 shell prompts are of the shapes that still ask, because the skills teach commands that carry the matter's path in a variable. That figure is an estimate from each command's shape, not a second build.

## A plugin cannot answer for the attorney

A first fix had the plugin's own permission check answer Allow for a matter run's own steps after one consent. The engine's types permit a hook to answer in either direction, and the app tests passed. In the real engine every prompt still reached the person. The debug log says why:

> `[cc-plugin-sec-default] senior-associate tried to lift a host's ask from a Bash call; the host's ask holds over the plugins you install (allowModsToOverrideDenyRules)`

An installed plugin may make a verdict stricter. It may not lift an ask unless the user turns on a Claude security setting that lets plugins override permission prompts, which this project does not ask attorneys to do. That code was not released.

## Decision

Recommend Auto for builds. The full build in Auto mode for the 1.3.0 release raised no prompts and no refusals, and Claude's own check reviews each step. The matter page says so where a build starts and where it waits, Help has an entry, and the README's "Permission prompts" section leads with it.

## Not tested

- Which Claude plans offer Auto.
- The new lines in the desktop app itself; the app tests draw them.
- Writing permission rules into the Matters folder with the plugin tightening the rest. Only a rule allowing every shell command would cover a build, and it would stay behind if the plugin were removed.
