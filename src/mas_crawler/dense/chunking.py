from dataclasses import dataclass

from transformers import PreTrainedTokenizerBase


@dataclass(frozen=True)
class TextChunk:
    position: int
    text: str
    start_char: int
    end_char: int


def split_text(
    text: str,
    tokenizer: PreTrainedTokenizerBase,
    *,
    chunk_size: int = 192,
    overlap: int = 32,
) -> list[TextChunk]:
    if chunk_size < 1 or not 0 <= overlap < chunk_size:
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size")
    if not tokenizer.is_fast:
        raise ValueError("Text splitting requires a fast tokenizer with offsets")

    encoded = tokenizer(
        text,
        add_special_tokens=False,
        truncation=False,
        return_offsets_mapping=True,
        return_attention_mask=False,
        return_token_type_ids=False,
    )
    offsets = encoded["offset_mapping"]
    chunks = []
    step = chunk_size - overlap

    for start in range(0, len(offsets), step):
        end = min(start + chunk_size, len(offsets))
        start_char = offsets[start][0]
        end_char = offsets[end - 1][1]

        chunks.append(
            TextChunk(
                position=len(chunks),
                text=text[start_char:end_char],
                start_char=start_char,
                end_char=end_char,
            )
        )

        if end == len(offsets):
            break

    return chunks
