# Hourly ChatGPT task specification

Status: **prepared only, not scheduled**. Activate this in a ChatGPT context that supports automations and exposes authenticated GitHub write access and code execution. The current session exposes no automation creation tool.

**Connection limitation:** the standard GitHub app in ChatGPT is read-only, according to [OpenAI's connection guide](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt). It cannot publish the development changes described below. A separately authorized GitHub CLI login has successfully published changes from the current execution environment. The full development loop needs that execution access and write authorization, a write-enabled Codex environment, or another authorized coding runner; no hourly runner has been configured here. See [GitHub setup](GITHUB_SETUP.md). A scheduled ChatGPT task alone does not supply these capabilities.

- Title: Improve the materials science agent toolkit
- Time zone: Etc/UTC
- Cadence: every hour at minute 00, second 00
- Schedule: `BEGIN:VEVENT\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=0;BYSECOND=0\nEND:VEVENT`
- Repository: https://github.com/calebhaines/materials-agent-toolkit (public).
- Delivery mode: open pull requests; the owner-authorized AI maintainer reviews and merges after independent review and all required CI pass.

Paste the following task prompt:

> Continue developing and improving the materials science and engineering toolkit at https://github.com/calebhaines/materials-agent-toolkit for automatic use by AI bots. Deliver changes as pull requests, review them independently and merge after all required CI pass, under the owner's standing authorization. Preserve the repository access and branch policies in docs/REPOSITORY_POLICY.md.
>
> At each hourly run, inspect the current repository, its AGENTS.md instructions, ROADMAP.md, BACKLOG.md, RUN_LOG.md, open pull requests and incomplete work. Use the repository as the source of persistent progress. Continue useful unfinished work before starting a duplicate task. Choose one highest-priority bounded improvement that advances scientific capability, agent usability, correctness, reproducibility or maintainability.
>
> Implement the change fully: publish strict schemas and explicit units/conventions; validate physical domains and numerical stability; document assumptions and scientific references; preserve tool versioning and provenance. Reuse established scientific libraries where appropriate. Prefer capable, tested operations over unverified breadth. Keep heavier simulations and data/model integrations modular.
>
> Verify the improvement with relevant analytical or independently validated scientific cases and the repository's required checks. Update the persistent backlog and development log with actual evidence, unresolved limits and the next useful task. Publish the change through the configured delivery mode only after required checks pass. Review pending work for correctness and repair regressions when they take priority. If there is no useful change, report that without creating an empty change.
>
> Report the completed improvement, GitHub commit or pull request link, verification evidence and next priority. If GitHub or execution access is unavailable, report the concrete blocker and preserve an actionable plan; do not claim that unexecuted changes were completed. Do not expose credentials or incur paid compute charges without authorization. If a prior run is still active, continue its recorded work or skip the overlapping run.

An active schedule alone does not guarantee access to code execution or repository writes. Verify the first run can perform and persist a real change before relying on unattended development. Keep recurring task instructions consistent with the owner's latest preferences.
