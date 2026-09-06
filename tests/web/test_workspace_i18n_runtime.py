"""Run the shipped translation runtime, including mutation and round-trip regressions."""

import json
import re
import shutil
import subprocess

from oceanpilot.web_i18n import CLIENT_I18N_SCRIPT, CLIENT_TRANSLATIONS

DOM = r"""
const assert=require('node:assert/strict');
const elements=[];
class Element {
 constructor(text='',attrs={}){this.nodeType=1;
this.attrs=attrs;this.children=[];elements.push(this);
if(text)this.children.push({nodeType:3,nodeValue:text,
parentElement:this});}
 matches(selector){return selector==='[data-no-i18n]'&&'data-no-i18n' in this.attrs;}
 closest(selector){return selector.includes('[data-no-i18n]')
&&'data-no-i18n' in this.attrs?this:null;
}
 hasAttribute(name){return name in this.attrs;}
 getAttribute(name){return this.attrs[name];}
 setAttribute(name,value){this.attrs[name]=value;}
 addEventListener(){}
}
const plain=new Element('查看详情'),dynamic=new Element('版本 2'),
original=new Element('查看详情',{'data-no-i18n':''});

const input=new Element('',{placeholder:'搜索规则','aria-label':'查询'});
const body=new Element();body.children=[plain,dynamic,original,input];
const storage=new Map();
global.localStorage={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)};
global.Node={TEXT_NODE:3,ELEMENT_NODE:1};global.NodeFilter={SHOW_ELEMENT:1,SHOW_TEXT:4};
let observeOptions,mutationCallback;
global.MutationObserver=class{constructor(callback){mutationCallback=callback;
}observe(_,options){observeOptions=options;}disconnect(){}};

global.document={body,cookie:'',readyState:'complete',documentElement:{},getElementById:()=>null,
 createTreeWalker(root){const all=[];function walk(node){
for(const child of node.children||[]){all.push(child);
walk(child);}}walk(root);return {nextNode:()=>all.shift()};
}};
global.window={dispatchEvent(){}};global.CustomEvent=class{};global.setInterval=()=>0;
"""


def run(assertions):
    result = subprocess.run(
        [shutil.which("node"), "-"],
        input=DOM + CLIENT_I18N_SCRIPT + assertions,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_switch_roundtrip_preserves_originals_and_observes_async_text_and_attributes():
    run("""
const i=window.oceanI18n;
i.setLanguage('en');
assert.equal(plain.children[0].nodeValue,'View details');
assert.equal(dynamic.children[0].nodeValue,'Revision 2');
assert.equal(original.children[0].nodeValue,'查看详情');
assert.equal(input.attrs.placeholder,'Search rules');
dynamic.children[0].nodeValue='版本 9';
input.attrs.placeholder='复核意见';mutationCallback([]);
assert.equal(dynamic.children[0].nodeValue,'Revision 9');
assert.equal(input.attrs.placeholder,'Review notes');
i.setLanguage('zh');
assert.equal(plain.children[0].nodeValue,'查看详情');
assert.equal(dynamic.children[0].nodeValue,'版本 9');
assert.equal(input.attrs.placeholder,'复核意见');
i.setLanguage('en');assert.equal(dynamic.children[0].nodeValue,'Revision 9');
assert.equal(storage.get('oceanpilot_workspace_language'),'en');
assert.equal(observeOptions.characterData,true);
assert.equal(observeOptions.attributes,true);
""")


def test_explicit_translation_target_does_not_depend_on_active_language():
    run("""
const i=window.oceanI18n;
assert.equal(i.getLanguage(),'zh');
assert.equal(i.translateTo('下一步：登记材料','en'),'Next step: Register material');
assert.equal(i.translateTo('已完成本案版本 12 的说明。','en'),
'Explanation completed for revision 12.');
assert.equal(i.translateTo('10 条 · 3 条 Demo Mapped · 4 个卡组织 · 4 份来源',
'en'),'10 rules · 3 demo mapped · 4 networks · 4 sources');

assert.equal(i.translateTo('登记版本 12','zh'),'登记版本 12');
""")


def test_every_reviewed_phrase_roundtrips_without_translating_original_input():
    phrases = [key for key in CLIENT_TRANSLATIONS if key != "中文"]
    run(
        """
const phrases=PHRASES_FOR_TEST;
for(const phrase of phrases){
 const e=new Element(phrase);body.children.push(e);
 window.oceanI18n.setLanguage('en');window.oceanI18n.apply(e);
 assert.equal(e.children[0].nodeValue,window.oceanI18n.translateTo(phrase,'en'),phrase);
 window.oceanI18n.setLanguage('zh');assert.equal(e.children[0].nodeValue,phrase,phrase);
 body.children.pop();
}
""".replace("PHRASES_FOR_TEST", json.dumps(phrases, ensure_ascii=False))
    )


def test_rule_and_evidence_catalogs_have_complete_english_display_text():
    from oceanpilot.domain.evidence_catalog import _CATALOG
    from oceanpilot.domain.reason_catalog import _LABELS
    from oceanpilot.web.summary_i18n import translate_display

    texts = list(_LABELS.values())
    for evidence in _CATALOG.values():
        texts.extend([evidence.label, evidence.why])
    for text in texts:
        assert not re.search(r"[\u3400-\u9fff]", translate_display(text)), text


def test_every_inline_action_has_a_packaged_handler_and_planned_buttons_are_disabled():
    from pathlib import Path

    from oceanpilot.web.rendering import resource_text

    root = Path(__file__).parents[2] / "src/oceanpilot/web/merchant"
    source = "\n".join(p.read_text() for p in root.glob("*.js"))
    markup = resource_text("merchant/shell.html")
    actions = set(re.findall(r'onclick="([a-zA-Z]+)\(', source + markup))
    definitions = set(re.findall(r"function ([a-zA-Z]+)\(", source))
    assert actions <= definitions
    assert len(actions) == 38
    planned = markup.split("planned-nav", 1)[1].split("</nav>", 1)[0]
    assert planned.count("disabled") == 3
