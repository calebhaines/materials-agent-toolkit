# GitHub connections for this project

The [standard GitHub app in ChatGPT](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt) is read-only. It can retrieve permitted repository content for analysis and search. It cannot push code or open pull requests. Repository selection controls what it can read; repeated login and public visibility do not provide write capabilities.

Use [Codex Cloud](https://developers.openai.com/codex/cloud/) for code changes and pull requests:

1. On the web or in the desktop app, choose **Work in > Cloud**, then **Select environment > Create environment**.
2. Choose `calebhaines/materials-agent-toolkit`, select **Get started**, and connect GitHub when prompted. Follow Codex's authorization flow to grant access to this repository.
3. Review the prepared setup, select **Publish**, and wait for **Environment published**.
4. Select **Start a new task**. Ask Codex to continue the repository using AGENTS.md, BACKLOG.md, ROADMAP.md and RUN_LOG.md, and deliver changes as pull requests.

The existing MCP implementation is complete and verified locally. Publication has not occurred. A patch and source archive preserve its changes. Download them from the conversation before moving to another environment: files and local branches in this ChatGPT workspace are not automatically present in a new Codex environment. Apply the prepared patch in a checkout based on the initial repository commit, or import the prepared source tree, then inspect the diff and run the documented checks before opening the pull request.

The repository is currently public because the owner changed its visibility while diagnosing access. Codex can work with private repositories when its GitHub authorization includes them.

The hourly ChatGPT task specification remains unactivated. A schedule and a read-only GitHub connection do not implement an autonomous development/publishing loop.
