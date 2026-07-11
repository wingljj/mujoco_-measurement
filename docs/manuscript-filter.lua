local removed_title = false

local restored_figures = {
  ['rendered_transport_snapshots_title_cropped.png'] = '../outputs/paper_figures/rendered_transport_snapshots_title_cropped.pdf',
  ['trajectory_3d_render_title_cropped.png'] = '../outputs/figures/trajectory_3d_render_title_cropped.pdf',
}

local function strip_figure_number(caption)
  return caption:gsub('^图%s*%d+%s*', '')
end

function Header(el)
  if not removed_title and el.level == 1 then
    removed_title = true
    return {}
  end
end

function CodeBlock(el)
  if el.classes:includes('math') then
    return pandoc.Para({pandoc.Math('DisplayMath', el.text)})
  end
end

function Str(el)
  el.text = el.text:gsub('✓', '是'):gsub('✗', '否')
  return el
end

function Image(el)
  local basename = el.src:match('([^/\\]+)$')
  if basename and restored_figures[basename] then
    el.src = restored_figures[basename]
    el.attributes.width = '15cm'
    return el
  end

  local stem = el.src:match('([^/\\]+)%.png$')
  if stem and stem:match('^fig%d%d_') then
    local caption = strip_figure_number(pandoc.utils.stringify(el.caption))
    el.caption = pandoc.Inlines({pandoc.Str(caption)})
    el.src = '../figures/pgfplots/build/' .. stem .. '.pdf'
    if stem:match('^fig0[58]_') then
      el.attributes.width = '8cm'
    else
      el.attributes.width = '15cm'
    end
  end
  return el
end

function Figure(el)
  local caption = strip_figure_number(pandoc.utils.stringify(el.caption))
  el.caption.long = pandoc.Blocks({pandoc.Plain({pandoc.Str(caption)})})
  el.caption.short = nil
  return el
end
