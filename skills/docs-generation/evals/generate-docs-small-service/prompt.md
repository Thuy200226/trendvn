---
tags: [docs-generation]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

This is a small mail-queue service we run for our own apps. Nobody has written proper docs for it and the README is just a stub. Please write the documentation for the project in the current folder: I want to be able to tell what it does and how to run it without reading the code, and someone new should be able to change it safely. Keep it short and make sure it is correct.
Input files: the whole mailq project (mailq/, tests/, Dockerfile, compose.yaml, .env.example, README.md, mailq-cli)
