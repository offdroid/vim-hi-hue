let s:plugin_root_dir = fnamemodify(resolve(expand('<sfile>:p')), ':h')

python3 << EOF
import sys
from os.path import normpath, join
import vim

plugin_root_dir = vim.eval('s:plugin_root_dir')
python_root_dir = normpath(join(plugin_root_dir, '..', 'python'))
sys.path.insert(0, python_root_dir)
import hihue
EOF

command! TryHighlightWord python3 hihue.try_highlight_word()
command! HiHueStatus python3 hihue.status()
command! HiHueDisconnect python3 hihue.disconnect()
command! HiHueDeregister python3 hihue.deregister()
command! -nargs=* HiHueConnect python3 hihue.connect(<f-args>)

let g:hiHue#disableAtStart = 0
if g:hiHue#disableAtStart == 0
    autocmd CursorMoved * python3 hihue.try_highlight_word()
endif 
