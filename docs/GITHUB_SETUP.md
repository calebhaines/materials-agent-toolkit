# GitHub connections for this project

The [standard GitHub app in ChatGPT](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt) is read-only. It can retrieve permitted repository content for analysis and search. That app cannot push code or open pull requests. Publishing can use a separately authorized GitHub CLI login in an execution environment, or Codex's GitHub integration.

## GitHub CLI device authentication

The CLI publishing route was verified in this project's current execution environment. Authenticate with repository permissions and workflow permissions (the MCP change updates CI):

```sh
env -u GH_TOKEN -u GITHUB_TOKEN gh auth login --hostname github.com --git-protocol https --web --scopes repo,workflow
```

Approve the device login in the browser, then verify `gh auth status` includes `repo` and `workflow`. The environment's `GH_TOKEN` or `GITHUB_TOKEN` can override the saved CLI login. To intentionally use the saved login, remove those variables for the command:

```sh
env -u GH_TOKEN -u GITHUB_TOKEN gh auth status
env -u GH_TOKEN -u GITHUB_TOKEN git push -u origin feat/mcp-agent-interface
env -u GH_TOKEN -u GITHUB_TOKEN gh pr create --base main --head feat/mcp-agent-interface --title 'Describe the completed change' --body-file /path/to/pr-description.md
```

Use an already-authorized saved login without asking the owner to authenticate again. A saved login may not carry into a new execution environment; verify access there before attempting publication. Do not include credential values in source or logs.

## Codex Cloud

Use [Codex Cloud](https://developers.openai.com/codex/cloud/) for code changes and pull requests:

1. On the web or in the desktop app, choose **Work in > Cloud**, then **Select environment > Create environment**.
2. Choose `calebhaines/materials-agent-toolkit`, select **Get started**, and connect GitHub when prompted. Follow Codex's authorization flow to grant access to this repository.
3. Review the prepared setup, select **Publish**, and wait for **Environment published**.
4. Select **Start a new task**. Ask Codex to continue the repository using AGENTS.md, BACKLOG.md, ROADMAP.md and RUN_LOG.md, and deliver changes as pull requests.

The MCP implementation is complete, verified, and published in [PR #1](https://github.com/calebhaines/materials-agent-toolkit/pull/1). It has not been merged. Other environments can fetch the published feature branch without transferring local artifacts from this conversation.

The repository is currently public because the owner changed its visibility while diagnosing access. A CLI login with repository scope, or Codex with the relevant GitHub authorization, can also work with private repositories the account is allowed to access.

The hourly ChatGPT task specification remains unactivated. A schedule and a read-only GitHub connection do not implement an autonomous development/publishing loop.
