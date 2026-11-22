from src.services.clip_copy_service import ClipCopy, clean_clip_copy


def test_copy_is_trimmed_without_links_and_with_clean_hashtags():
    cleaned = clean_clip_copy(ClipCopy(
        instagram_caption='  "Watch this https://example.com/x now"  ',
        instagram_hashtags=["#Wild", "wild", "no way!", "#a b"],
        youtube_title="T" * 150,
        youtube_description="See www.example.com for more",
        youtube_hashtags=["#Shorts", "Shorts"],
    ))
    assert cleaned["instagram"]["caption"] == "Watch this now"
    assert cleaned["instagram"]["hashtags"] == ["#Wild", "#noway", "#ab"]
    assert len(cleaned["youtube"]["title"]) == 100
    assert "example.com" not in cleaned["youtube"]["description"]
    assert cleaned["youtube"]["hashtags"] == ["#Shorts"]
