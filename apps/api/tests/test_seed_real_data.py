from apps.api.scripts.seed_real_data import classify_signal, parse_google_news_rss, strip_html


def test_strip_html_compacts_text() -> None:
    assert strip_html("<div>Hello <b>world</b><br/>again</div>") == "Hello world again"


def test_classify_signal_prefers_regulatory_and_security_markers() -> None:
    assert classify_signal("RBI imposes compliance penalty after cyber incident") in {"security_event", "regulatory_event"}
    assert classify_signal("Bank appoints new chief digital officer") == "leadership_change"
    assert classify_signal("Bank launches new onboarding partnership") == "digital_initiative"


def test_parse_google_news_rss_reads_basic_items() -> None:
    xml_text = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Axis Bank launches security upgrade</title>
          <link>https://news.google.com/test-story</link>
          <description><![CDATA[<p>Axis Bank expanded cyber controls.</p>]]></description>
          <pubDate>Mon, 20 Apr 2026 08:30:00 GMT</pubDate>
          <source url="https://example.com">Example News</source>
        </item>
      </channel>
    </rss>
    """
    items = parse_google_news_rss(xml_text)
    assert len(items) == 1
    assert items[0]["title"] == "Axis Bank launches security upgrade"
    assert items[0]["source"] == "Example News"
    assert items[0]["description"] == "Axis Bank expanded cyber controls."
    assert items[0]["published_at"] is not None
