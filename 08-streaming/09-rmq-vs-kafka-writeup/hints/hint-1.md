# Hint 1

Start by sketching the RMQ setup you know from production: How many producers are feeding it (Scrapy spiders)? How many queues or exchanges? How many competing consumer processes, and do they all want the same data or different subsets? Does anyone retry failed messages?

Then, for each of the three requests (multi-reader, replay, consumer groups), think about what a queue doesn't do that a log would. A queue loses messages once they're acked; there is no "read it again from the start" or "two independent readers at different speeds."

Don't try to write the perfect answer yet—just map "here's what we do now" to "here's what we can't do."
