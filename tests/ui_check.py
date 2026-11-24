from streamlit.testing.v1 import AppTest

at = AppTest.from_file("../app.py", default_timeout=20).run()
assert not at.exception, at.exception
for q in ("How can I improve my monthly savings?", "What about food?"):
    at.chat_input[0].set_value(q).run()
    assert not at.exception, at.exception
print(len(at.chat_message), "chat messages;", len(at.metric), "metrics;", len(at.warning) + len(at.error) + len(at.info), "alert/info boxes")
