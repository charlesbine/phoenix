"""Pick a random quote from the programmingexcuses.com cached data and display it."""

from random import choice
import json

from pheonix import app_db
from pheonix.types import PreprocessorResult


ENDPOINT = "http://programmingexcuses.com/"
APPLET_NAME = "programming_excuses"


def main():
    app = app_db.get_app_by_name(APPLET_NAME)
    excuse = choice(QUOTES)
    # code to save the encoded file to the data file
    app.data_file.write_text(json.dumps({"excuse": excuse}))
    return PreprocessorResult(excuse)


def get_quote() -> str:
    import requests
    import bs4

    resp = requests.get(ENDPOINT)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.text)
    return soup.body.div.center.text


def get_n_quotes(n: int) -> list[str]:
    return list(set(get_quote() for _ in range(n)))


QUOTES = [
    "Did you check for a virus on your system?",
    "Don't worry, that value is only wrong half of the time",
    "Even though it doesn't work, how does it feel?",
    "I broke that deliberately to do some testing",
    "I can't test everything",
    "I couldn't find any examples of how that can be done anywhere else in the project",
    "I couldn't find any examples of how that can be done anywhere online",
    "I didn't anticipate that I would make any errors",
    "I didn't receive a ticket for it",
    "I have never seen that before in my life",
    "I have too many other high priority things to do right now",
    "I haven't been able to reproduce that",
    "I haven't had the chance to run that code yet",
    "I haven't touched that code in weeks",
    "I heard there was a solar flare today",
    "I thought I fixed that",
    "I'll have to fix that at a later date",
    "I'm not familiar with it so I didn't fix it in case I made it worse",
    "I'm not getting any error codes",
    "I'm surprised it works as well as it does",
    "It must be a hardware problem",
    "It must be because of a leap second",
    "It probably won't happen again",
    "It was working in my head",
    "It worked yesterday",
    "It works for me",
    "It works, but it's not been tested",
    "It would have taken twice as long to build it properly",
    "It would take too long to rewrite the code from scratch",
    "It's a known bug with the server software",
    "It's a remote vendor issue",
    "It's always been like that",
    "It's an unexpected emergent behaviour of several last minute abstractions",
    "It's just some unlucky coincidence",
    "It's never shown unexpected behaviour like this before",
    "It's not a code problem - our users need more training",
    "Management insisted we wouldn't need to waste our time writing unit tests",
    "Maybe somebody forgot to pay our hosting company",
    "My time was split in a way that meant I couldn't do either project properly",
    "No one told me so I was forced to assume which way to do that",
    "Nobody asked me how long it would actually take",
    "Oh, you said you DIDN'T want that to happen?",
    "Our code quality is no worse than anyone else in the industry",
    "Our internet connection must not be working",
    "THIS can't be the source of THAT",
    "That behaviour is in the original specification",
    "That code was written by the last guy",
    "That feature would be outside of the scope",
    "That important email must have been marked as spam",
    "That's interesting, how did you manage to make it do that?",
    "The accounting department must have cancelled that subscription",
    "The client wanted it changed at the last minute",
    "The code is compiling",
    "The download must have been corrupted",
    "The person responsible doesn't work here anymore",
    "The program has never collected that information",
    "The project manager said no one would want that feature",
    "The request must have dropped some packets",
    "The unit test doesn't cover that eventuality",
    "There must be something strange in your data",
    "There was too little data to bother with the extra functionality at the time",
    "There were too many developers working on that same thing",
    "There's currently a problem with our hosting company",
    "This code was not supposed to go in to production yet",
    "We didn't have enough time to peer review the final changes",
    "We should have updated our software years ago",
    "We spent three months debugging it because we only had one month to build it",
    "Well at least we know not to try that again",
    "What did I tell you about using parts of the system you don't understand?",
    "What did you type in wrong to get it to crash?",
    "Why do you want to do it that way?",
    "You can't use that version on your system",
    "You must have done something wrong",
    "You must have the wrong version",
    "Your browser must be caching the old content",
]


if __name__ == "__main__":
    main()
