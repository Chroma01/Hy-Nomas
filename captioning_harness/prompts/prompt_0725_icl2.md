# In-Context Final Output Examples

The following two examples demonstrate only the required final-turn output schema, exact Subject-token usage, Action and Camera wrapper formatting, bilingual structural alignment, chronological segment organization, and the required language-specific `description_change` prefixes.

These examples do **not** describe the current video. Never copy or infer their subjects, identities, attributes, actions, camera motions, timestamps, segment counts, scene details, wording, or other facts into the current output. During first and intermediate turns, continue to follow the required turn-local draft schema; do not output the complete bilingual final schema early. Use these examples only as formatting and annotation-pattern references when producing the final summary.

Every current video must be analyzed independently from its own visible evidence. The current video supplied segment boundaries remain authoritative.

## Example 1

```json
{
  "english_json": {
    "perspective_view": "third-person observer",
    "Style": "real-world footage",
    "subject_list": [
      {
        "subject_id": "<|Subject1|>",
        "display_name": "adult handling green stems",
        "subject_attribute": "Light-skinned forearms and hands emerging from a black long-sleeved garment; face and body remain outside the frame."
      }
    ],
    "segments": [
      {
        "start_time": "00:00.000",
        "end_time": "00:12.680",
        "visual_description_long": "A tight close-up presents the interior of and the space immediately above a large, pale white plastic container. A dark, irregular heap of leafy plant material rests out of focus in the lower-left corner. A black horizontal structure occupies the upper-left background, while a blurred blue-gray area appears intermittently along the right edge. Several short green stems with smooth outer surfaces, pale fibrous interiors, and jagged split ends fill the central foreground. Soft, natural-looking illumination and shallow depth of field emphasize the torn fibers and fine surface textures. <Camera1>The externally positioned camera maintains a slightly elevated side angle, with subtle handheld drift, minor focus softness, and no major reframing</Camera1>. Pale strips become exposed along the split ends, while the dark heap remains stationary in the background. Multiple stems now display pointed, splintered tips and light-colored interiors beneath their green surfaces. The bundle becomes more compact, with shortened green shafts projecting in several directions. Several upright green ends and pale torn slivers remain visible above the container as the close-up concludes.",
        "description_change": null,
        "contained_actions": [
          {
            "start_time": "00:00.000",
            "end_time": "00:03.000",
            "action_description": "<Action1><|Subject1|> holds several green stems, pinches loose outer layers, bends individual pieces, and separates them above the container</Action1>."
          },
          {
            "start_time": "00:03.000",
            "end_time": "00:06.000",
            "action_description": "<Action2><|Subject1|> grips separate stems, pulls away fibrous coverings, rotates the pieces, and gathers the stripped sections into a small bundle</Action2>."
          },
          {
            "start_time": "00:06.000",
            "end_time": "00:09.500",
            "action_description": "<Action3><|Subject1|> aligns the bundle, transfers pieces between grips, and repeatedly plucks or tears away thin dangling fibers</Action3>."
          },
          {
            "start_time": "00:09.500",
            "end_time": "00:12.680",
            "action_description": "<Action4><|Subject1|> lifts a short piece, returns it to the bundle, pinches another split end, and continues rearranging and cleaning the remaining stems</Action4>."
          }
        ]
      }
    ]
  },
  "chinese_json": {
    "perspective_view": "third-person observer",
    "Style": "真实视频",
    "subject_list": [
      {
        "subject_id": "<|Subject1|>",
        "display_name": "处理绿色茎秆的成年人",
        "subject_attribute": "浅肤色的前臂和手从黑色长袖衣物中露出；面部和身体始终位于画面之外。"
      }
    ],
    "segments": [
      {
        "start_time": "00:00.000",
        "end_time": "00:12.680",
        "visual_description_long": "特写镜头呈现一个大型浅白色塑料容器的内部及其正上方空间。左下角散放着一堆深色、不规则的叶状植物材料，处于失焦状态。黑色横向结构占据左上方背景，右侧边缘则间歇出现模糊的蓝灰色区域。数根表面光滑的绿色短茎占据中央前景，可见浅色纤维状内部和参差不齐的裂口。柔和且近似自然的光线配合浅景深，突出了撕裂的纤维和细微的表面纹理。<Camera1>外部机位保持略微俯视的侧面角度，仅有轻微的手持漂移和焦点柔化，没有明显重新构图</Camera1>。 裂开的末端逐渐露出浅色条状物，背景中的深色材料堆保持静止。 多根茎秆此时显露出尖锐的碎裂端部，以及绿色表层下方的浅色内部。 材料束变得更加紧凑，缩短的绿色茎段朝不同方向伸出。 特写结束时，容器上方仍可见数个直立的绿色末端和浅色撕裂薄片。",
        "description_change": null,
        "contained_actions": [
          {
            "start_time": "00:00.000",
            "end_time": "00:03.000",
            "action_description": "<Action1><|Subject1|>握住数根绿色茎秆，捏起松散的外层，弯折单根材料，并在容器上方将其分开</Action1>。"
          },
          {
            "start_time": "00:03.000",
            "end_time": "00:06.000",
            "action_description": "<Action2><|Subject1|>分别抓住茎秆，拉掉纤维状外皮，转动材料，并将剥过的部分收拢成一小束</Action2>。"
          },
          {
            "start_time": "00:06.000",
            "end_time": "00:09.500",
            "action_description": "<Action3><|Subject1|>整理成束的材料，在不同抓握位置之间转移各段，并反复摘除或撕掉悬垂的细纤维</Action3>。"
          },
          {
            "start_time": "00:09.500",
            "end_time": "00:12.680",
            "action_description": "<Action4><|Subject1|>提起一小段材料，将其放回材料束，捏住另一处裂口，并继续整理和清除剩余茎秆上的碎屑</Action4>。"
          }
        ]
      }
    ]
  }
}
```

## Example 2

```json
{
  "english_json": {
    "perspective_view": "third-person observer",
    "Style": "real-world footage",
    "subject_list": [
      {
        "subject_id": "<|Subject1|>",
        "display_name": "protective-suited operator",
        "subject_attribute": "An adult-sized operator wearing a bulky olive-green protective suit with a padded hood, rounded helmet, clear face visor, dark gloves, black straps, and an attached hose or cable, initially standing beside a raised planting bed and holding a long green-and-black pole toward inspection equipment."
      },
      {
        "subject_id": "<|Subject2|>",
        "display_name": "younger GATE officer",
        "subject_attribute": "A younger adult man wearing a black cap with yellow GATE lettering, a fitted black short-sleeved shirt, dark camouflage trousers, black boots, a duty belt, and an earpiece, initially standing in a sunlit parking lot beside another GATE officer."
      },
      {
        "subject_id": "<|Subject3|>",
        "display_name": "older GATE officer with microphone",
        "subject_attribute": "An older adult man with short gray hair wearing a black cap with yellow GATE lettering, a black armored vest marked GATE over a dark camouflage uniform, and black boots, initially standing beside the younger officer while holding a logo-marked handheld microphone."
      }
    ],
    "segments": [
      {
        "start_time": "00:00.000",
        "end_time": "00:08.000",
        "visual_description_long": "A sunlit outdoor dirt area lies beside a pale beige perimeter wall topped with coils of wire. A faded rectangular notice or emblem is mounted on the wall. Tree trunks and a raised planting bed occupy the shaded left side, while dry leaves, stones, twigs, and exposed pipes cover the uneven ground. Strong sunlight casts sharply defined shadows across the wall and soil. The pole extends diagonally toward a compact mechanical assembly positioned before a black rectangular panel. <Camera1>The handheld camera moves forward and pans right from a medium view, following the pole toward the equipment and gradually narrowing the composition</Camera1>. The handled panel bears white “VIDISCO” and “BlazeX” markings, four corner guides, and a central crosshair. A metal mechanism with several narrow hanging components stands immediately before the panel on thin supports and a white padded base. A curved cable runs from the panel area toward the right edge. <Camera2>The camera pushes into a close view of the pole tip, mechanical assembly, and marked panel with slight handheld shake</Camera2>. A small olive-colored boxlike device with a dark circular front, a red top button, yellow markings, and a short cable becomes visible on the ground in the lower foreground. Long shadows stretch across the dirt around the device and panel. <Camera3>The camera then eases backward and slightly left, widening to include more of the pole and the foreground device while retaining the panel and assembly on the right</Camera3>.",
        "description_change": null,
        "contained_actions": [
          {
            "start_time": "00:00.000",
            "end_time": "00:02.000",
            "action_description": "<Action1><|Subject1|> stands in the left foreground in a bulky olive-green protective suit with a padded hood, helmet, clear visor, dark gloves, black straps, and an attached hose or cable while gripping a long green-and-black pole with both hands</Action1>."
          },
          {
            "start_time": "00:02.000",
            "end_time": "00:08.000",
            "action_description": "<Action2><|Subject1|> keeps the far end of the pole aligned with the mechanical assembly and makes small, controlled positioning adjustments without releasing the two-handed grip</Action2>."
          }
        ]
      },
      {
        "start_time": "00:08.000",
        "end_time": "00:21.000",
        "visual_description_long": null,
        "description_change": "Compared to the previous segment, the view leaves the wall-side inspection setup and opens onto a paved parking lot marked with yellow lines, rows of dark and light-colored cars, leafy trees, several distant uniformed figures, and a large pale building under intense backlighting and green lens flare. <Camera1>The handheld camera pans quickly left along the pole, passes the raised planting bed and building corner, and swings into the adjoining parking lot</Camera1>. The panel and small ground device leave the frame as parked vehicles fill the foreground and background. <Camera2>The camera advances across the lot with noticeable shake and strong flare from the low sun behind the distant building</Camera2>. <Camera3>The camera pushes from a wide parking-lot view into a medium waist-up two-shot</Camera3>. <Camera4>The camera closes in further and shifts slightly right as lens-flare spots cross the frame</Camera4>.",
        "contained_actions": [
          {
            "start_time": "00:08.000",
            "end_time": "00:10.000",
            "action_description": "<Action1><|Subject1|> continues gripping the long pole with both hands while keeping the far end directed toward the inspection panel, then disappears from view as the framing turns away</Action1>."
          },
          {
            "start_time": "00:10.000",
            "end_time": "00:14.000",
            "action_description": "<Action2><|Subject2|> stands in a black GATE cap, fitted black shirt, camouflage trousers, duty belt, and earpiece while speaking and pointing forward with a partially extended right hand; <|Subject3|> stands alongside in a black GATE cap, dark camouflage uniform, and marked armored vest while raising a logo-marked microphone toward <|Subject2|></Action2>."
          },
          {
            "start_time": "00:14.000",
            "end_time": "00:17.500",
            "action_description": "<Action3><|Subject2|> continues speaking and alternates between a pinched-finger gesture and an open hand near chest height, while <|Subject3|> holds the microphone steady and watches attentively</Action3>."
          },
          {
            "start_time": "00:17.500",
            "end_time": "00:21.000",
            "action_description": "<Action4><|Subject2|> extends the right arm fully across the foreground to indicate an area off-screen right, then begins drawing the arm back while continuing smaller explanatory gestures; <|Subject3|> turns the gaze in the indicated direction and keeps the microphone positioned between <|Subject2|> and <|Subject3|></Action4>."
          }
        ]
      },
      {
        "start_time": "00:21.000",
        "end_time": "00:35.969",
        "visual_description_long": null,
        "description_change": "Compared to the previous segment, the visible scene, background, and other-object layout remain materially unchanged. <Camera1>The handheld camera holds a close two-shot with minor lateral drift and persistent green lens flare from the upper-left sunlight</Camera1>. <Camera2>The framing subtly pans and widens to the right, exposing more space between the parked cars</Camera2>. <Camera3>The camera edges closer on the microphone side of the two-shot while preserving the parking-lot activity in the right background</Camera3>.",
        "contained_actions": [
          {
            "start_time": "00:21.000",
            "end_time": "00:24.500",
            "action_description": "<Action1><|Subject2|> continues speaking with small pinched-finger and open-hand gestures near chest height while looking off-screen right, as <|Subject3|> keeps the microphone directed toward <|Subject2|> and watches the same area</Action1>."
          },
          {
            "start_time": "00:24.500",
            "end_time": "00:27.500",
            "action_description": "<Action2><|Subject2|> sweeps the right hand outward once more and then lowers it, while <|Subject3|> shifts attention farther right and draws the microphone closer to the chest</Action2>."
          },
          {
            "start_time": "00:27.500",
            "end_time": "00:30.500",
            "action_description": "<Action3><|Subject1|> enters from the right background and walks leftward while carrying the long pole horizontally with both hands; <|Subject2|> pauses the larger gestures and looks toward the activity, while <|Subject3|> turns toward <|Subject2|> and raises the microphone to begin responding</Action3>."
          },
          {
            "start_time": "00:30.500",
            "end_time": "00:33.000",
            "action_description": "<Action4><|Subject3|> speaks into the microphone and gestures with the free hand, alternating between an open palm and a downward indication toward the lot; <|Subject2|> faces <|Subject3|> and listens; <|Subject1|> stops in the right background, steadies the pole horizontally, and briefly raises one hand toward the helmet or visor</Action4>."
          },
          {
            "start_time": "00:33.000",
            "end_time": "00:35.969",
            "action_description": "<Action5><|Subject3|> continues speaking, points toward the right, and finishes with a level sweeping hand motion; <|Subject2|> remains attentive with hands lowered; <|Subject1|> maintains a wide stance and makes small adjustments to the pole’s angle while holding it across the body</Action5>."
          }
        ]
      }
    ]
  },
  "chinese_json": {
    "perspective_view": "third-person observer",
    "Style": "真实视频",
    "subject_list": [
      {
        "subject_id": "<|Subject1|>",
        "display_name": "身穿防护服的操作员",
        "subject_attribute": "一名成人体型的操作员，身穿厚重的橄榄绿色防护服，配有软垫兜帽、圆形头盔、透明面罩、深色手套、黑色束带以及连接的软管或线缆；最初站在抬高的种植池旁，手持一根绿色与黑色相间的长杆朝向检测设备。"
      },
      {
        "subject_id": "<|Subject2|>",
        "display_name": "较年轻的GATE警员",
        "subject_attribute": "一名较年轻的成年男子，戴着带有黄色GATE字样的黑色帽子，身穿修身黑色短袖上衣、深色迷彩长裤和黑色靴子，系有装备腰带并佩戴耳机；最初与另一名GATE警员并排站在阳光照射的停车场中。"
      },
      {
        "subject_id": "<|Subject3|>",
        "display_name": "手持麦克风的年长GATE警员",
        "subject_attribute": "一名留有灰色短发的年长成年男子，戴着带有黄色GATE字样的黑色帽子，在深色迷彩制服外穿着标有GATE字样的黑色防护背心，并穿着黑色靴子；最初手持一支带标志的麦克风站在较年轻的警员旁边。"
      }
    ],
    "segments": [
      {
        "start_time": "00:00.000",
        "end_time": "00:08.000",
        "visual_description_long": "一片阳光照射的室外泥土地位于一面浅米色围墙旁，墙顶设有成圈的铁丝。墙上安装着一块褪色的矩形告示或徽记。树干和抬高的种植池占据左侧阴影区域，干树叶、石块、细枝和裸露管道散布在凹凸不平的地面上。强烈阳光在墙面和泥土上投下边缘清晰的阴影。 长杆斜向延伸至位于黑色矩形面板前方的一套紧凑机械组件。<Camera1>手持摄影机从中景向前移动并向右摇摄，沿着长杆移向设备，同时逐渐收紧构图</Camera1>。 带提手的面板上有白色“VIDISCO”和“BlazeX”字样、四个角部定位标记以及中央十字准线。一套带有数个细长悬挂部件的金属机构紧邻面板前方，由细支架和白色软垫底座支撑。一根弯曲线缆从面板区域延伸至画面右侧边缘。<Camera2>摄影机推进至长杆尖端、机械组件和标记面板的近景，并伴有轻微的手持抖动</Camera2>。一个小型橄榄色盒状装置出现在下方前景地面上，带有深色圆形前端、顶部红色按钮、黄色标记和一根短线缆。装置和面板周围的泥地上延伸着长长的阴影。<Camera3>摄影机随后略微后退并向左移动，扩大画面以纳入更多长杆和前景装置，同时将面板与机械组件保留在右侧</Camera3>。",
        "description_change": null,
        "contained_actions": [
          {
            "start_time": "00:00.000",
            "end_time": "00:02.000",
            "action_description": "<Action1><|Subject1|>站在左侧前景，身穿带软垫兜帽、头盔、透明面罩、深色手套、黑色束带以及连接软管或线缆的厚重橄榄绿色防护服，并用双手握住一根绿色与黑色相间的长杆</Action1>。"
          },
          {
            "start_time": "00:02.000",
            "end_time": "00:08.000",
            "action_description": "<Action2><|Subject1|>保持长杆远端对准机械组件，并在不松开双手握持的情况下进行小幅、受控的位置调整</Action2>。"
          }
        ]
      },
      {
        "start_time": "00:08.000",
        "end_time": "00:21.000",
        "visual_description_long": null,
        "description_change": "与前一片段相比，画面离开墙边的检测装置，转而展现一处带黄色标线的铺装停车场，其中排列着深色和浅色车辆、枝叶茂盛的树木、数名远处的制服人员以及一栋浅色大型建筑，强烈逆光和绿色镜头光斑覆盖画面。 <Camera1>手持摄影机沿长杆快速向左摇摄，掠过抬高的种植池和建筑转角，转入相邻的停车场</Camera1>。面板和地面上的小型装置离开画面，停放的车辆占据前景和背景。<Camera2>摄影机带着明显抖动穿过停车场向前移动，远处建筑后方的低角度阳光产生强烈光斑</Camera2>。 <Camera3>摄影机从停车场广角画面推进至腰部以上的双人中景</Camera3>。 <Camera4>摄影机进一步靠近并略微向右移动，镜头光斑从画面中穿过</Camera4>。",
        "contained_actions": [
          {
            "start_time": "00:08.000",
            "end_time": "00:10.000",
            "action_description": "<Action1><|Subject1|>继续用双手握住长杆并保持远端朝向检测面板，随后随着画面转开而消失在视野中</Action1>。"
          },
          {
            "start_time": "00:10.000",
            "end_time": "00:14.000",
            "action_description": "<Action2><|Subject2|>戴着黑色GATE帽，身穿修身黑色上衣、迷彩长裤并系有装备腰带、佩戴耳机，一边说话一边用部分伸出的右手向前指示；<|Subject3|>戴着黑色GATE帽，身穿深色迷彩制服和带标记的防护背心站在旁边，同时将带标志的麦克风举向<|Subject2|></Action2>。"
          },
          {
            "start_time": "00:14.000",
            "end_time": "00:17.500",
            "action_description": "<Action3><|Subject2|>继续说话，并在胸前高度交替做出捏指手势和张开手掌的动作，而<|Subject3|>稳定握住麦克风并专注观看</Action3>。"
          },
          {
            "start_time": "00:17.500",
            "end_time": "00:21.000",
            "action_description": "<Action4><|Subject2|>将右臂完全伸过前景以指示画外右侧区域，随后开始收回手臂并继续做出较小的解释性手势；<|Subject3|>将视线转向所指方向，并让麦克风保持在<|Subject2|>与<|Subject3|>之间</Action4>。"
          }
        ]
      },
      {
        "start_time": "00:21.000",
        "end_time": "00:35.969",
        "visual_description_long": null,
        "description_change": "与前一片段相比，可见场景、背景和其他物体的布局在实质上保持不变。 <Camera1>手持摄影机维持近距离双人画面，伴有轻微横向漂移，左上方阳光持续产生绿色镜头光斑</Camera1>。 <Camera2>构图轻微向右摇摄并扩大，显露出停放车辆之间的更多空间</Camera2>。 <Camera3>摄影机从麦克风一侧靠近双人画面，同时保留右侧背景中的停车场活动</Camera3>。",
        "contained_actions": [
          {
            "start_time": "00:21.000",
            "end_time": "00:24.500",
            "action_description": "<Action1><|Subject2|>继续说话，在胸前高度做出小幅捏指和张开手掌的手势，同时望向画外右侧；<|Subject3|>保持麦克风朝向<|Subject2|>并注视同一区域</Action1>。"
          },
          {
            "start_time": "00:24.500",
            "end_time": "00:27.500",
            "action_description": "<Action2><|Subject2|>再次向外挥动右手后将其放低，而<|Subject3|>把注意力进一步转向右侧，并将麦克风收至更靠近胸前的位置</Action2>。"
          },
          {
            "start_time": "00:27.500",
            "end_time": "00:30.500",
            "action_description": "<Action3><|Subject1|>从右侧背景进入，双手水平携带长杆向左行走；<|Subject2|>停止较大幅度的手势并看向该处活动，而<|Subject3|>转向<|Subject2|>并举起麦克风开始回应</Action3>。"
          },
          {
            "start_time": "00:30.500",
            "end_time": "00:33.000",
            "action_description": "<Action4><|Subject3|>对着麦克风说话，并用空闲的手做动作，在张开手掌与向下指示停车场之间交替；<|Subject2|>面向<|Subject3|>聆听；<|Subject1|>停在右侧背景，水平稳住长杆，并短暂抬起一只手靠近头盔或面罩</Action4>。"
          },
          {
            "start_time": "00:33.000",
            "end_time": "00:35.969",
            "action_description": "<Action5><|Subject3|>继续说话，指向右侧，并以一次水平扫动手势结束；<|Subject2|>放低双手保持专注；<|Subject1|>保持双腿分开的站姿，在将长杆横持于身前的同时小幅调整长杆角度</Action5>。"
          }
        ]
      }
    ]
  }
}
```
