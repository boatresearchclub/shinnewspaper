//選手コメント取得 引数 登番(当日コメント)
function funcToDayComment( argTouban )
{
	var strComment = '';
	var strTouban = argTouban;
	if( strTouban === '3081'){
		strComment = '数字のないエンジンだけど、悪くはなかった。';
	}else if( strTouban === '3211'){
		strComment = '２班では似た感じ。ひとまずこのまま行ってみる。';
	}else if( strTouban === '3257'){
		strComment = '回転不足だけど、微調整ぐらいで行けそう。';
	}else if( strTouban === '3587'){
		strComment = '回転が合ってなくて、あまり良くなかった。';
	}else if( strTouban === '3589'){
		strComment = '回転が上がっていたので、止める方向で調整する。';
	}else if( strTouban === '3591'){
		strComment = 'スタート特訓は周りと一緒くらい。';
	}else if( strTouban === '3605'){
		strComment = '多分、悪くないと思う。';
	}else if( strTouban === '3606'){
		strComment = '特徴がなかったし、足併せでは中村守成選手の方が良かった。';
	}else if( strTouban === '3826'){
		strComment = '自分の形にして行き足は良かったけど、伸びは売り切れていた。';
	}else if( strTouban === '3838'){
		strComment = '行き足は少し不安定だけど、伸びている感じはあった。';
	}else if( strTouban === '3867'){
		strComment = '起こしはちょっと良くなかった。';
	}else if( strTouban === '3908'){
		strComment = 'スタートが届くし、起こしも悪くない。違和感はなかった。';
	}else if( strTouban === '3915'){
		strComment = '回転の上がりは悪くなかった。少し回り過ぎかな。';
	}else if( strTouban === '3989'){
		strComment = '伸びが良くなかったし、芳しくなかった。';
	}else if( strTouban === '4058'){
		strComment = '悪さは感じなかったけど、いいとも思わなかった。';
	}else if( strTouban === '4064'){
		strComment = 'そのまま行って足は普通。気になるところはなかった。';
	}else if( strTouban === '4074'){
		strComment = '押していないし、操縦性も良くない。';
	}else if( strTouban === '4112'){
		strComment = 'そのまま行って悪くはないと思う。';
	}else if( strTouban === '4116'){
		strComment = '乗りづらさがあったので、ペラを叩いた。';
	}else if( strTouban === '4122'){
		strComment = '出て行くことも、下がることもなかった。';
	}else if( strTouban === '4134'){
		strComment = '班で下がらなかったし、普通はあると思う。';
	}else if( strTouban === '4182'){
		strComment = 'ペラを大幅に叩いたら壊れそうな感じで…。';
	}else if( strTouban === '4195'){
		strComment = '高野哲史選手と足併せをしたら一緒くらいだった。';
	}else if( strTouban === '4351'){
		strComment = 'スタートの行き足は良さそうだが、その先は大したことがない。';
	}else if( strTouban === '4380'){
		strComment = 'ペラを叩いたけど、回ってなくて行き足が鈍い。';
	}else if( strTouban === '4411'){
		strComment = 'ペラを少し叩いて余裕のある感じだった。';
	}else if( strTouban === '4468'){
		strComment = '伸び寄りのセッティングだけど、そこまで伸びなかった。';
	}else if( strTouban === '4512'){
		strComment = '変な感じはしなかったし、普通かな。外周りを点検する。';
	}else if( strTouban === '4630'){
		strComment = 'ペラ調整をしてターン回りはまずまず。伸びは普通。';
	}else if( strTouban === '4636'){
		strComment = '班でズリ下がることはなかった。';
	}else if( strTouban === '4674'){
		strComment = 'いまいちだった。部品交換を考える。';
	}else if( strTouban === '4705'){
		strComment = '悪くはないけど、重たい感じを解消させたい。';
	}else if( strTouban === '4754'){
		strComment = 'ペラを片面叩いてスタート特訓の違和感はなかった。';
	}else if( strTouban === '4861'){
		strComment = '行き足や回り足は悪くなかったし、レースは出来そう。';
	}else if( strTouban === '4894'){
		strComment = '聞いていたほど伸びで下がる感じはなかった。';
	}else if( strTouban === '4905'){
		strComment = '自分の回転に叩いて行き足は良さそうだった。';
	}else if( strTouban === '4930'){
		strComment = '悪くはなかった。ペラ調整だけをやった。';
	}else if( strTouban === '4945'){
		strComment = '起こしはいいけど、軽い感じがした。';
	}else if( strTouban === '4976'){
		strComment = '新ペラに換わっているし参考外。';
	}else if( strTouban === '5018'){
		strComment = 'ペラを最近の形に叩いている途中なので…。';
	}else if( strTouban === '5038'){
		strComment = 'ジワジワ伸びて行くし、前検としては合格かな。';
	}else if( strTouban === '5126'){
		strComment = '前検一番時計だけど、出足系だと思う。';
	}else if( strTouban === '5135'){
		strComment = '出て行く伸びはないけど、ターン回りの押しはあった。';
	}else if( strTouban === '5210'){
		strComment = '出足が好きな感じでターン回りに不安はない。';
	}else if( strTouban === '5384'){
		strComment = '下がらなかったし、行き足が良さそう。';
	}else if( strTouban === '5427'){
		strComment = '伸びそうな感触があったし、いいエンジンだと思う。';
	}else{
	//例外
		strComment = '';
	}
	return strComment;
}
//選手コメント当日New取得(引数 登番,順番1～4,レース番号(1走目に2走目は表示しないため、0は全表示),コメント表示=1.タイプを表示=2,レース番号を表示=3)
function funcToDayNewComment( argTouban , argOrder , argRacenum , argType )
{
	var strComment = '';
	var strTouban = argTouban;
	var strOrder = argOrder;
	var intRaceNum = argRacenum;
	var strType = argType;
	if( strTouban === '3081'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3081'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3081'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3081'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3211'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3211'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3211'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3211'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3257'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3257'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3257'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3257'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3587'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3587'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3587'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3587'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3589'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3589'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3589'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3589'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3591'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3591'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3591'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3591'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3605'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3605'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3605'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3605'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3606'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3606'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3606'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3606'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3826'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3826'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3826'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3826'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3838'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3838'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3838'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3838'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3867'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3867'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3867'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3867'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3908'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3908'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3908'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3908'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3915'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3915'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3915'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3915'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3989'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3989'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3989'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '3989'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4058'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4058'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4058'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4058'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4064'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4064'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4064'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4064'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4074'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4074'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4074'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4074'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4112'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4112'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4112'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4112'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4116'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4116'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4116'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4116'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4122'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4122'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4122'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4122'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4134'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4134'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4134'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4134'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4182'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4182'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4182'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4182'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4195'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4195'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4195'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4195'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4351'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4351'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4351'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4351'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4380'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4380'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4380'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4380'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4411'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4411'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4411'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4411'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4468'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4468'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4468'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4468'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4512'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4512'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4512'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4512'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4630'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4630'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4630'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4630'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4636'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4636'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4636'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4636'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4674'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4674'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4674'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4674'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4705'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4705'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4705'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4705'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4754'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4754'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4754'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4754'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4861'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4861'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4861'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4861'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4894'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4894'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4894'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4894'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4905'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4905'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4905'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4905'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4930'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4930'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4930'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4930'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4945'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4945'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4945'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4945'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4976'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4976'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4976'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '4976'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5018'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5018'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5018'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5018'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5038'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5038'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5038'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5038'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5126'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5126'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5126'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5126'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5135'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5135'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5135'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5135'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5210'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5210'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5210'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5210'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5384'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5384'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5384'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5384'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5427'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5427'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5427'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else if( strTouban === '5427'){
		if( strOrder === '1'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '2'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '3'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else if( strOrder === '4'){
			if( intRaceNum >= 0){
				if( strType === '1' ){
					strComment = '';
				}else if( strType === '2' ){
					strComment = '';
				}else if( strType === '3' ){
					strComment = '0';
				}else{
					strComment = '';
				}
			}else{
				strComment = '';
			}
		}else{
			strComment = '';
		}
	}else{
	//例外
		strComment = '';
	}
	return strComment;
}
