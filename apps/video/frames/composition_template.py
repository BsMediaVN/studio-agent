"""HTML skeleton for the frames composition (kept separate to keep
``composition.py`` focused on logic). ``.format()`` slots: width/height/total/
bg/fg/accent/font/title/clips + the optional B-roll slots bg_css/bg_block/
kenburns (empty strings when no segment carries an image → flat-bg output).
"""

HTML_TEMPLATE = """<!doctype html>
<html lang="vi" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {width}px; height: {height}px; overflow: hidden;
        background: {bg}; color: {fg}; font-family: {font}; }}
      .brand {{ position: absolute; top: 56px; right: 72px; font-size: 34px;
        font-weight: 800; color: {accent}; letter-spacing: -1px; }}
      .card {{ position: absolute; top: 56px; left: 72px; display: flex;
        align-items: center; gap: 20px; }}
      .avatar {{ width: 76px; height: 76px; border-radius: 50%; display: flex;
        align-items: center; justify-content: center; font-size: 36px;
        font-weight: 800; color: #0a0e14; }}
      .name {{ font-size: 40px; font-weight: 700; }}
      .cap {{ position: absolute; left: 50%; transform: translateX(-50%);
        bottom: 120px; width: 78%; text-align: center; font-size: 56px;
        font-weight: 600; line-height: 1.3; text-shadow: 0 2px 12px rgba(0,0,0,.6); }}{bg_css}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}"
         data-width="{width}" data-height="{height}">
{bg_block}      <div class="brand">{title}</div>
{clips}
    </div>
    <script>
      // Empty paused timeline — required by hyperframes lint; visibility is
      // handled by class="clip" timing, so NO opacity tweens (those hide clips).
      // Background images may add transform-only Ken Burns tweens (safe).
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});{kenburns}
    </script>
  </body>
</html>
"""
