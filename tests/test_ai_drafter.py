import asyncio

from ai_drafter import AIDraftingEngine, build_email

def lead(**overrides):
    base = {"business_name": "Apex Dental", "niche": "dentist", "city": "Austin",
            "website_url": "http://www.apexdental.com", "issues": []}
    base.update(overrides)
    return base

def test_opens_with_strongest_issue():
    subject, body = build_email(lead(issues=["old_copyright:2017", "http", "no_viewport"]), "legacy_redesign")
    assert "phone" in subject
    assert "apexdental.com" in body
    assert "pinch and zoom" in body

def test_old_copyright_mentions_year():
    _, body = build_email(lead(issues=["old_copyright:2017"]), "legacy_redesign")
    assert "© 2017" in body

def test_no_website_pitch_never_mentions_their_site_layout():
    _, body = build_email(lead(issues=["no_website"], rating=4.8, review_count=112), "no_website")
    assert "couldn't find a website" in body
    assert "4.8 stars from 112 reviews" in body
    assert "modern version of your homepage" not in body

def test_ai_automation_offer_matches_strategy():
    _, body = build_email(lead(website_url="https://bright.com", issues=["manual_form"]), "ai_automation")
    assert "pick a time" in body
    assert "online booking" in body

def test_every_email_has_opt_out_and_no_placeholders():
    for strategy, issues in [("legacy_redesign", ["http"]), ("ai_automation", ["no_booking"]), ("no_website", ["no_website"])]:
        _, body = build_email(lead(issues=issues), strategy)
        assert "no thanks" in body
        assert "[" not in body and "{" not in body

def test_generate_without_llm_includes_subject():
    engine = AIDraftingEngine(use_llm=False)
    message = asyncio.run(engine.generate_outreach_message(lead(issues=["http"]), strategy="legacy_redesign"))
    assert message.startswith("Subject: ")

def test_llm_output_validation_rejects_drift():
    engine = AIDraftingEngine(use_llm=False)
    assert engine._llm_output_ok("Hi, I noticed apexdental.com shows a warning.", lead())
    assert not engine._llm_output_ok("Hi [Name], our practice provides care", lead())
    assert not engine._llm_output_ok("Dear owner, ...", lead())

def test_niche_reads_naturally():
    _, body = build_email(lead(niche="hvac", issues=["no_viewport"]), "legacy_redesign")
    assert "looking for an HVAC company in Austin" in body
    _, body = build_email(lead(niche="optometrist", issues=["no_booking"]), "ai_automation")
    assert "look for an optometrist" in body

def test_site_errors_pitch():
    subject, body = build_email(lead(issues=["no_viewport", "site_errors"]), "legacy_redesign")
    assert "error messages" in subject
    assert "error messages instead of the normal site" in body
