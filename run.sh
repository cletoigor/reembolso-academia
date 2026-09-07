#!/bin/bash
export HOME=/Users/igorcleto
export PATH=/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.8/bin:/usr/local/bin:/usr/bin:/bin

LOG=/Users/igorcleto/automacoes/reembolso-academia/cron.log
echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG"

/opt/homebrew/bin/claude -p "Execute /reembolso-academia agora. Busque o comprovante no Gmail, converta, preencha o form, envie, notifique no Slack e adicione evento concluído no Google Calendar." --allowedTools "Bash,Read,WebSearch,WebFetch,mcp__claude_ai_Gmail__search_threads,mcp__claude_ai_Gmail__get_thread,mcp__claude_ai_Slack__slack_search_users,mcp__claude_ai_Slack__slack_send_message,mcp__claude_ai_Google_Calendar__create_event,mcp__claude_ai_Google_Calendar__list_events" >> "$LOG" 2>&1

echo "exit: $?" >> "$LOG"
