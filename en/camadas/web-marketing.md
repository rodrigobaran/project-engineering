<!-- mirror of camadas/web-marketing.md sha256:1020b49f968f6d20b6a0cd03ed7090e20596eeb6322271cde7b482cd9315477b; edit the Portuguese source first -->
# Layer: web and marketing

For systems that generate content and publish to external channels (website, social networks).

**Dominant risk:** publishing something wrong or exposed in public. Publishing is irreversible in practice.
A draft that mentions a client, a partner, an IP address, an internal domain or a configuration is a leak, even with
perfect code.

## The planner asks
- Which source does the content come from, and is it on the list of allowed sources?
- Does it involve a third party (partner, client)? Which channel, and what are its size and format limits?
- Does the change create or alter any route that publishes? (If so, it is class A.)

## The reviewer looks for
- A publishing route that does not go through the approval record.
- A social network credential in code, a log, a fixture or an error message.
- A forbidden term that escapes the filter (upper case, accents, split across two lines, inside a URL).
- A broken link, text above the channel's limit.

## CI runs, in addition to the core
- The forbidden-terms filter over every draft in the tests.
- A test proving that no publication happens without an approval record.
- Size limit per channel; website build and link check.

## Fixed rules
- Nothing is published without a recorded approval (who, when, which version of the text). In any phase.
- Social network credentials live only in the publishing service, never in the environment of the agent that writes code.
- Content sources are read, never written.
- Generated text is product: it is evaluated by sampling (a 1 to 5 score from the project owner), with a metric separate from the factory's.
