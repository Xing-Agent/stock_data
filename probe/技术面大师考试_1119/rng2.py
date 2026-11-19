exec(open('rng.py').read().split("go('震荡·假跌破·目标中轴+对边')")[0])
for b in [30,45,90]: go(f'震荡·假跌破·箱体{b}根4H',box_n=b)
# 组合：顺势引擎(上涨才做多, 上涨里空单半仓) + 震荡区间只做底部多(60根)
x1=pd.read_csv('lin_frame.csv') if False else None
exec(open('lin.py').read().split("score('③现状")[0].split("def mk(lr):",1)[0])
