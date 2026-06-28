@echo off
REM Sync local-dev branch to Gitea for cloud review
git add .
git commit -m "Local subagent implementation" --allow-empty
git push origin local-dev
echo Code pushed to Gitea. Ready for Cloud Review.
