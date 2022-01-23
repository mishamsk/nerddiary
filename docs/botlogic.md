# Bot logic

- Bot Started / Restarted
    - Read config
    - Read all user configs
    - Create admin object (handlers etc.)
    - Add handlers
    - Reload all user poll jobs (`handlers.reload_user_poll_jobs`)
        - Remind all users who chat with bot that it was restarted
        - For each poll with reminder
            - Create chat context if not exist for
            - Remove all jobs
            - If not `bot_config.bot_debug`: set daily job, else daily but in 5 seconds from now
- Bot Idle
    - Start command (`handlers.start`)
        - New user
            - **missing into text**
            - Reload all user poll jobs (`handlers.reload_user_poll_jobs`)
                - For each poll with reminder
                    - Create chat context
                    - If not `bot_config.bot_debug`: set daily job, else daily but in 5 seconds from now
        - Existing users
            - **missing special logic**
    - Job triggered
        - Always runs through module `job` for wrapping, see `job.run_handler_from_job`
- `handlers.handler` decorator
    - Check if `ActivePollContext` or `ChatContext`
    1. Possible scenarios
        1. Jobs ***[update = None, context.job.context is JobContext]***
            1. Chat job update
                1. Not related to an active poll
                    1. Starting a poll ***[context.job.context is NewPollJobContext]***
                    2. *Report in the future*
                2. Related to an active poll = delay ***[context.job.context is ActivePollJobContext]***
            2. Non-chat job update
                1. *None so far*
        2. Updates ***[update is Update]***
            1. Command ***[update.callback_query is None]***
                1. Not related to an active poll
                    1. /start
                    2. /help **missing special logic**
                    3. /stop **missing special logic**
                    4. /[poll]
                2. Related to an active poll
                    1. cancel command
            2. Callback query ***[update.callback_query is not None]***
                1. Not related to an active poll
                    1. poll select
                2. Related to an active poll
                    1. answer
            3. Regular message ***[update.callback_query is None]***
                1. *None so far*
        3. Handler sub-handler-call

