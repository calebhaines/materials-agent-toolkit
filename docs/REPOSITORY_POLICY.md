# Repository contribution and maintenance policy

The owner, `calebhaines`, authorizes the AI maintainer to develop, independently review and merge tested changes. The repository remains publicly readable, while code contributions and pull request creation are limited to collaborators. Only the owner's account is currently a collaborator.

## Enforced controls

| Control | Setting |
| --- | --- |
| Pull request creation | `collaborators_only`, permanent |
| Write access | Owner only; no additional collaborators, deploy keys or pending invitations |
| `main` updates | Pull requests with up-to-date branches |
| Required checks | `validate (3.11)`, `validate (3.12)`, `validate (3.13)`, `base-install` |
| Check source | GitHub Actions app ID `15368` |
| Administrator enforcement | Enabled |
| Force pushes and deletion of `main` | Disabled |
| History and conversations | Linear history and resolved conversations required |
| Actions tokens | Read permissions; cannot approve PR reviews |
| External contributor workflows | Manual approval required for all external contributors |

GitHub forbids formal approval by a PR's author. Because the only collaborator is the owner, the branch requires zero formal approvals while still requiring a PR and all checks. The authorized maintainer must perform independent review, verify the exact reviewed commit and merge only after required checks succeed. This configuration keeps automated owner maintenance possible without granting another account access or bypassing protections.

## Limits and future work

Public cloning and forking remain available. A fork does not confer upstream write access, and a non-collaborator cannot open an upstream PR under the creation policy. Public issues and comments remain available as feedback; they do not authorize changing access, credentials or maintenance policy.

Do not add collaborators, deploy keys, rule bypasses or broad workflow-token permissions without explicit owner authorization. Maintain the controls when changing CI job names or repository settings. Verify live settings through the GitHub API; the snapshot in [.github/repository-policy.json](../.github/repository-policy.json) records the intended policy, not an automatic configuration service.

The hourly development task is still unactivated. Repository maintenance authorization and access controls do not themselves create a schedule.
