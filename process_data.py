import pandas as pd
import numpy as np
import time
import gc

data_perc = 0.5

raw_start = time.time()

def compute_score(df, feature, feature_id):
    attrs = df[(df[feature]==feature_id) & (df['is_attributed']==1)]
    n_attrs = attrs.shape[0]
    del attrs
    gc.collect()

    clicks = df[df[feature]==feature_id]
    n_clicks = clicks.shape[0]
    del clicks
    gc.collect()

    if n_attrs==0:
        return -n_clicks
    return n_attrs/n_clicks

def sort_features_by_attr_proba(df, features):
    sorted_features = {}

    for feature in features:
        print('\n--- sorting {}'.format(feature))
        start = time.time()

        scores = {}
        feature_ids = set(df[feature])
        for feature_id in feature_ids:
            scores[feature_id] = compute_score(df, feature, feature_id)
        sorted_ids = sorted(feature_ids, key=lambda feature_id: scores[feature_id], reverse=True)
        del scores
        gc.collect()

        indexes = {}
        for feature_id in feature_ids:
            indexes[feature_id] = sorted_ids.index(feature_id)
        del feature_ids, sorted_ids
        gc.collect()

        df[feature] = df[feature].apply(lambda x: indexes[x]).astype('uint16')
        sorted_features[feature] = indexes

        print('{:.2f}s to sort {}'.format(time.time()-start, feature))

    return sorted_features

def generate_count_features(df, groupbys):
    for groupby in groupbys:
        print('\n--- grouping by {}'.format(groupby))
        suffix = '_'+('_'.join(groupby))

        start = time.time()
        df['n'+suffix] = df.groupby(groupby)['ip'].transform('count').astype('uint32')
        gc.collect()
        print('{:.2f}s to generate feature {}'.format(time.time()-start, 'n'+suffix))

def transform(df):
    sorted_features = sort_features_by_attr_proba(df, ['app', 'os', 'device', 'channel'])

    start = time.time()
    datetimes = pd.to_datetime(df['click_time'])
    df['moment'] = (60*datetimes.dt.hour + datetimes.dt.minute).astype('uint16')
    print('\n{:.2f}s to generate feature moment'.format(time.time()-start))

    groupbys = [['ip'], ['ip', 'app'],
                ['ip', 'os'], ['ip', 'os', 'app'],
                ['ip', 'device'], ['ip', 'device', 'app'],
                ['ip', 'os', 'device'], ['ip', 'os', 'device', 'app'],
                ['ip', 'channel'], ['ip', 'channel', 'app']]
    generate_count_features(df, groupbys)

    return sorted_features

train_columns = ['ip', 'app', 'device', 'os', 'channel', 'click_time', 'is_attributed']
test_columns  = ['ip', 'app', 'device', 'os', 'channel', 'click_time', 'click_id']
dtypes = {
    'click_id'      : 'uint32',
    'ip'            : 'uint32',
    'app'           : 'uint16',
	'device'        : 'uint16',
    'os'            : 'uint16',
    'channel'       : 'uint16',
    'is_attributed' : 'uint8'
}

# reading raw data
train_size_total = 184903890
train_size = int(data_perc*train_size_total)
start = time.time()
skiprows = range(1,train_size_total-train_size+1) if data_perc < 1.0 else None
print('reading input/train.csv')
data_train = pd.read_csv('input/train.csv', usecols=train_columns, dtype=dtypes, nrows=train_size, skiprows=skiprows)
print('{:.2f}s to load train data'.format(time.time()-start))

start = time.time()
print('reading input/test_supplement.csv')
data_test = pd.read_csv('input/test_supplement.csv', usecols=test_columns, dtype=dtypes)
print('{:.2f}s to load test data'.format(time.time()-start))


# extracting interesting features
def get_processed_data(data_train, data_test):
    start = time.time()
    train_size = data_train.shape[0]
    combine = pd.concat([data_train, data_test])
    combine['click_id'] = combine['click_id'].fillna(0).astype('uint32')
    combine['is_attributed'] = combine['is_attributed'].fillna(0).astype('uint8')
    del data_train, data_test
    gc.collect()
    print('{:.2f}s to concatenate train/test data'.format(time.time()-start))

    sorted_features = transform(combine)

    data_train = combine[:train_size].drop(columns=['click_id', 'ip', 'click_time'])
    data_test = combine[train_size:].drop(columns=['is_attributed'])

    del combine
    gc.collect()

    return (data_train, data_test, sorted_features)

start = time.time()
data_train, data_test, sorted_features = get_processed_data(data_train, data_test)
process_time = time.time()-start
print('\n{:.2f}s to process data ({:.2f} lines/s)'.format(process_time, (data_train.shape[0]+data_test.shape[0])/process_time))

# saving csv
start = time.time()
data_train.to_csv('intermediary/train_processed.csv', index=False)
del data_train
gc.collect()
print('{:.2f}s to create intermediary/train_processed.csv'.format(time.time()-start))

start = time.time()
data_submission = pd.read_csv('input/test.csv')
for feature in sorted_features:
    indexes = sorted_features[feature]
    data_submission[feature] = data_submission[feature].apply(lambda x: indexes[x]).astype('uint16')

data_test = pd.merge(data_submission, data_test, how='inner', on=['ip', 'app', 'device', 'os', 'channel', 'click_time']) \
              .drop(columns=['ip', 'click_time', 'click_id_y']) \
              .drop_duplicates(subset=['click_id_x']) \
              .sort_values(by=['click_id_x']) \
              .rename(columns={'click_id_x': 'click_id'})
del data_submission
gc.collect()
print('{:.2f}s to choose submission subset'.format(time.time()-start))

start = time.time()
data_test.to_csv('intermediary/test_processed.csv', index=False)
del data_test
gc.collect()
print('{:.2f}s to create intermediary/test_processed.csv'.format(time.time()-start))

print('{:.2f}s to process data'.format(time.time()-raw_start))
