import numpy as np
import tensorflow as tf
import tensorflow.contrib.slim as slim

from dataset import Reader


class Network:
    def __init__(self, args):
        self.BATCH_SIZE = args.size
        self.train_pattern = "dataset/data/segmented_set1/*.tfr"
        self.test_pattern = "dataset/data/segmented_set2/*.tfr"
        self.train_reader = Reader.Reader(args, self.train_pattern)
        self.test_reader = Reader.Reader(args, self.test_pattern)
        self.STEP = args.step
        self.IS_TRAINING = True
        self.HEIGHT = args.height
        self.WIDTH = args.width
        self.LRATE = args.lrate
        self.RESTORE = args.restore
        self.UPDATE = args.update
        self.cnntype = args.cnn
        self.train_logs_path = 'network/train_logs'
        self.test_logs_path = 'network/test_logs'
        self.chkpt_file = self.train_logs_path + "/model.ckpt"
        self.classes_num = 6
        self.model()
        self.train_writer = tf.summary.FileWriter(self.train_logs_path, graph=self.graph)
        self.test_writer = tf.summary.FileWriter(self.test_logs_path, graph=self.graph)

    def model(self):
        with tf.Graph().as_default() as self.graph:
            self.x = tf.placeholder(dtype=tf.float32, shape=(self.BATCH_SIZE, self.HEIGHT, self.WIDTH, 3), name="input")
            self.y = tf.placeholder(dtype=tf.int32, shape=(1,), name='labels')
            # flatten_x = tf.reshape(x, (-1, height, width, 3))
            if self.cnntype == 'inception':
                print('Using Inception model')
                net = self.inception_cnn(self.x)
            elif self.cnntype == 'vgg16':
                print('Using VGG16 model')
                net = self.vgg16(self.x)
            else:
                print('Using common cnn block')
                net = self.cnn(self.x)
            size = np.prod(net.get_shape().as_list()[1:])
            output = self.rnn(net, size)
            logits = self.dense(output)
            self.calc_accuracy(logits, self.y)

            with tf.name_scope('Cost'):
                self.cross_entropy = slim.losses.sparse_softmax_cross_entropy(logits=logits, labels=self.y,
                                                                              scope='cross_entropy')
                tf.summary.scalar("cross_entropy", self.cross_entropy)
            with tf.name_scope('Optimizer'):
                self.global_step = tf.Variable(0, name='global_step', trainable=False)
                self.optimizer = tf.train.AdamOptimizer(self.LRATE)
                self.train_step = slim.learning.create_train_op(self.cross_entropy, self.optimizer, self.global_step,
                                                                aggregation_method=tf.AggregationMethod.EXPERIMENTAL_TREE)
            self.summary_op = tf.summary.merge_all()
            self.saver = tf.train.Saver()

    def cnn(self, input):
        with slim.arg_scope([slim.conv2d], stride=1, weights_initializer=tf.contrib.layers.xavier_initializer_conv2d(),
                            trainable=self.IS_TRAINING):
            with tf.variable_scope('Convolution', [input]):
                conv1 = slim.conv2d(input, 32, [1, 1], stride=2, scope='Conv1',
                                    normalizer_fn=slim.batch_norm,
                                    normalizer_params={'is_training': self.IS_TRAINING})
                pool2 = slim.max_pool2d(conv1, [3, 3], scope='Pool1', stride=1)
                conv2 = slim.conv2d(pool2, 32, [3, 3], scope='Conv2')
                pool3 = slim.max_pool2d(conv2, [3, 3], scope='Pool2', stride=1)
                return slim.conv2d(pool3, 32, [3, 3], stride=2, scope='Conv3')

    def inception_cnn(self, inputs):
        conv1 = slim.conv2d(inputs, 32, [3, 3], stride=2, padding='VALID', scope='Conv2d_1a_3x3')
        conv2 = slim.conv2d(conv1, 32, [3, 3], stride=2, padding='VALID', scope='Conv2d_2a_3x3')
        inc_inputs = slim.conv2d(conv2, 64, [3, 3], scope='Conv2d_2b_3x3')

        with slim.arg_scope([slim.conv2d, slim.avg_pool2d, slim.max_pool2d], trainable=self.IS_TRAINING, stride=1,
                            padding='SAME'):
            with tf.variable_scope('BlockInceptionA', [inc_inputs]):
                with tf.variable_scope('IBranch_0'):
                    ibranch_0 = slim.conv2d(inc_inputs, 96, [1, 1], scope='IConv2d_0a_1x1')
                with tf.variable_scope('IBranch_1'):
                    ibranch_1_conv1 = slim.conv2d(inc_inputs, 64, [1, 1], scope='IConv2d_0a_1x1')
                    ibranch_1 = slim.conv2d(ibranch_1_conv1, 96, [3, 3], scope='IConv2d_0b_3x3')
                with tf.variable_scope('IBranch_2'):
                    ibranch_2_conv1 = slim.conv2d(inc_inputs, 64, [1, 1], scope='IConv2d_0a_1x1')
                    ibranch_2_conv2 = slim.conv2d(ibranch_2_conv1, 96, [3, 3], scope='IConv2d_0b_3x3')
                    ibranch_2 = slim.conv2d(ibranch_2_conv2, 96, [3, 3], scope='IConv2d_0c_3x3')
                with tf.variable_scope('IBranch_3'):
                    ibranch_3_pool = slim.avg_pool2d(inc_inputs, [3, 3], scope='IAvgPool_0a_3x3')
                    ibranch_3 = slim.conv2d(ibranch_3_pool, 96, [1, 1], scope='IConv2d_0b_1x1')
                inception = tf.concat(axis=3, values=[ibranch_0, ibranch_1, ibranch_2, ibranch_3])
            with tf.variable_scope('BlockReductionA', [inception]):
                with tf.variable_scope('RBranch_0'):
                    rbranch_0 = slim.conv2d(inception, 384, [3, 3], stride=2, padding='VALID', scope='RConv2d_1a_3x3')
                with tf.variable_scope('RBranch_1'):
                    rbranch_1_conv1 = slim.conv2d(inception, 192, [1, 1], scope='RConv2d_0a_1x1')
                    rbranch_1_conv2 = slim.conv2d(rbranch_1_conv1, 224, [3, 3], scope='RConv2d_0b_3x3')
                    rbranch_1 = slim.conv2d(rbranch_1_conv2, 256, [3, 3], stride=2, padding='VALID',
                                            scope='RConv2d_1a_3x3')
                with tf.variable_scope('RBranch_2'):
                    rbranch_2 = slim.max_pool2d(inception, [3, 3], stride=2, padding='VALID', scope='RMaxPool_1a_3x3')
            return tf.concat(axis=3, values=[rbranch_0, rbranch_1, rbranch_2])

    def vgg16(self, inputs):
        with slim.arg_scope([slim.conv2d, slim.fully_connected],
                            activation_fn=tf.nn.relu,
                            trainable=self.IS_TRAINING,
                            weights_initializer=tf.truncated_normal_initializer(0.0, 0.01),
                            weights_regularizer=slim.l2_regularizer(0.0005)):
            net = slim.repeat(inputs, 2, slim.conv2d, 64, [3, 3], scope='conv1')
            net = slim.max_pool2d(net, [2, 2], scope='pool1')
            net = slim.repeat(net, 2, slim.conv2d, 128, [3, 3], scope='conv2')
            net = slim.max_pool2d(net, [2, 2], scope='pool2')
            net = slim.repeat(net, 3, slim.conv2d, 256, [3, 3], scope='conv3')
            net = slim.max_pool2d(net, [2, 2], scope='pool3')
            net = slim.repeat(net, 3, slim.conv2d, 512, [3, 3], scope='conv4')
            net = slim.max_pool2d(net, [2, 2], scope='pool4')
            net = slim.repeat(net, 3, slim.conv2d, 512, [3, 3], scope='conv5')
            net = slim.max_pool2d(net, [2, 2], scope='pool5')
            net = slim.fully_connected(net, 4096, scope='fc6')
            net = slim.dropout(net, 0.5, scope='dropout6')
            net = slim.fully_connected(net, 4096, scope='fc7')
            net = slim.dropout(net, 0.5, scope='dropout7')
            net = slim.fully_connected(net, 1000, activation_fn=None, scope='fc8')
        return net

    def rnn(self, net, size):
        with tf.variable_scope('GRU_RNN_cell'):
            rnn_inputs = tf.reshape(net, (-1, self.BATCH_SIZE, size))
            cell = tf.contrib.rnn.LSTMCell(100)
            init_state = cell.zero_state(1, dtype=tf.float32)
            rnn_outputs, _ = tf.nn.dynamic_rnn(cell, rnn_inputs, initial_state=init_state)
            return tf.reduce_mean(rnn_outputs, axis=1)

    def dense(self, output):
        with tf.name_scope('Dense'):
            return slim.fully_connected(output, self.classes_num, scope="Fully-connected")

    def calc_accuracy(self, logits, y):
        with tf.name_scope('Accuracy'):
            prediction = tf.cast(tf.arg_max(logits, dimension=1), tf.int32)
            self.accuracy = tf.contrib.metrics.accuracy(labels=y, predictions=prediction)
            tf.summary.scalar("accuracy", self.accuracy)

    @staticmethod
    def get_nb_params_shape(shape):
        """
        Computes the total number of params for a given shap.
        Works for any number of shapes etc [D,F] or [W,H,C] computes D*F and W*H*C.
        """
        nb_params = 1
        for dim in shape:
            nb_params = nb_params * int(dim)
        return nb_params

    def count_number_trainable_params(self):
        """
        Counts the number of trainable variables.
        """
        tot_nb_params = 0
        for trainable_variable in slim.get_trainable_variables():
            shape = trainable_variable.get_shape()  # e.g [D,F] or [W,H,C]
            current_nb_params = self.get_nb_params_shape(shape)
            tot_nb_params = tot_nb_params + current_nb_params
        return tot_nb_params

    def begin_training(self):
        self.IS_TRAINING = True

        with tf.Session(graph=self.graph) as sess:
            if self.RESTORE:
                self.saver.restore(sess, self.chkpt_file)
                print("Model restored.")
            else:
                sess.run(tf.local_variables_initializer())
                sess.run(tf.global_variables_initializer())

            print("Number of trainable variables:", self.count_number_trainable_params())
            for el in slim.get_trainable_variables():
                print(el, el.shape)

            correct_answers = []
            ten_step_acc = []
            i = 1
            while True:
                label, example = self.train_reader.get_random_example()
                feed_dict = {self.x: example, self.y: label}

                if i % 10 == 0:
                    run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
                    run_metadata = tf.RunMetadata()
                    _, summary, global_step, accuracy = sess.run(
                        [self.train_step, self.summary_op, self.global_step, self.accuracy],
                        feed_dict=feed_dict, options=run_options, run_metadata=run_metadata)

                    if accuracy == 1:
                        correct_answers.append(1)
                    print('[train] Accuracy on step {}: {}'.format(global_step, accuracy))

                    self.train_writer.add_run_metadata(run_metadata, 'step{}'.format(global_step), global_step)
                    self.train_writer.add_summary(summary, global_step)
                    print('[train] Adding run metadata for', global_step)

                    ten_step_acc.append(sum(correct_answers) / 10)
                    print('[train] Accuracy for 10 steps:', sum(correct_answers) / 10)

                    save_path = self.saver.save(sess, self.chkpt_file)
                    print("[train] Model saved in file: %s" % save_path)

                    correct_answers = []

                    if i % 100 == 0:
                        print('[train] Epoch accuracy:', sum(ten_step_acc) / len(ten_step_acc))
                        ten_step_acc = []
                        self.begin_test()
                        self.IS_TRAINING = True

                else:
                    _, summary, global_step, accuracy = sess.run(
                        [self.train_step, self.summary_op, self.global_step, self.accuracy],
                        feed_dict=feed_dict)
                    self.train_writer.add_summary(summary, global_step)
                    if accuracy == 1:
                        correct_answers.append(1)
                    print('[train] Accuracy on step {}: {}'.format(global_step, accuracy))
                i += 1

    def begin_test(self):
        self.IS_TRAINING = False

        with tf.Session(graph=self.graph) as sess:
            self.saver.restore(sess, self.chkpt_file)
            print("Model restored")
            print("Number of trainable variables:", self.count_number_trainable_params())

            correct_answers = []
            ten_step_acc = []
            sc = 1
            while sc <= 100:
                label, example = self.test_reader.get_random_example()
                feed_dict = {self.x: example, self.y: label}

                if sc % 10 == 0:
                    run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
                    run_metadata = tf.RunMetadata()
                    summary, global_step, accuracy = sess.run(
                        [self.summary_op, self.global_step, self.accuracy],
                        feed_dict=feed_dict, options=run_options, run_metadata=run_metadata)
                    self.test_writer.add_run_metadata(run_metadata, 'step{}'.format(global_step), global_step)
                    self.test_writer.add_summary(summary, global_step)
                    print('[test] Adding run metadata for', global_step)

                    if accuracy == 1:
                        correct_answers.append(1)
                    print('[test] Accuracy on step {}: {}'.format(global_step, accuracy))

                    ten_step_acc.append(sum(correct_answers) / 10)
                    print('[test] Accuracy for 10 steps:', sum(correct_answers) / 10)

                    correct_answers = []
                    if sc % 100 == 0:
                        print('[test] Test accuracy:', sum(ten_step_acc) / len(ten_step_acc))
                        ten_step_acc = []

                else:
                    summary, global_step, accuracy = sess.run(
                        [self.summary_op, self.global_step, self.accuracy],
                        feed_dict=feed_dict)
                    self.test_writer.add_summary(summary, global_step)
                    if accuracy == 1:
                        correct_answers.append(1)
                    print('[test] Accuracy on step {}: {}'.format(global_step, accuracy))
                sc += 1
