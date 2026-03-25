load("http.star", "http")
load("render.star", "render")
load("schema.star", "schema")


LOCAL_SERVER = "http://127.0.0.1:7002/data"
ENDPOINT = "programming_excuses.json"

# font = "CG-pixel-3x5-mono"
font = "tb-8"

def main(config):
    quote = get_quote(config)
    quote_format = format_quote(quote)

    scroll_opt = config.str("speed", "50")
    return render.Root(
        delay = int(scroll_opt),  #speed up scroll text
        show_full_animation = True,
        child = render.Column(children = [quote_format]),
    )

######################################################
#functions
def split_sentence(sentence, span, **kwargs):
    #split long sentences along with long words

    sentence_new = ""
    for word in sentence.split(" "):
        if len(word) >= span:
            sentence_new += split_word(word, span, **kwargs) + " "

        else:
            sentence_new += word + " "

    return sentence_new

def split_word(word, span, join_word = False):
    #split long words

    word_split = []

    for i in range(0, len(word), span):
        word_split.append(word[i:i + span])
    if join_word:
        return " ".join(word_split)
    else:
        return word_split

######################################################
#functions to get data


def get_quote(config):
    endpoint = LOCAL_SERVER + "/" + ENDPOINT
    rep = http.get(endpoint)
    if rep.status_code != 200:
        fail("Request to %s failed with %d", endpoint, rep.status_code)
    else:
        quote = rep.json()["excuse"]

    return quote

def format_quote(quote):
    #formats quote text
    frame_data = []
    for (idx, line) in enumerate(quote.splitlines()):
        if idx % 2 == 0:
            ctmp = "#fff"
        else:
            ctmp = "#c8c8fa"
        line_tmp = split_sentence(line, 12, join_word = True)  #combine and split words correctly
        line_format = render.WrappedText(content = line_tmp, width = 64, color = ctmp, font = font, linespacing = 1)
        frame_data.append(line_format)

    return render.Marquee(
        height = 64,
        offset_start = 64,
        offset_end = 64,
        scroll_direction = "vertical",
        child = render.Column(
            children = frame_data,
        ),
    )
