use motionbricks_core::{Codebook, Error, MAX_ELEMENTS};

#[test]
fn exhaustive_small_spaces_against_independent_coordinates() {
    // Enumerate head coordinates, not the implementation's repeated modulo loop.
    for entries in 1..=5 {
        let data: Vec<f32> = (0..3 * entries * 2).map(|v| v as f32 - 13.0).collect();
        let book = Codebook::new(3, entries, 2, data.clone()).unwrap();
        for a in 0..entries {
            for b in 0..entries {
                for c in 0..entries {
                    let overall = a + b * entries + c * entries * entries;
                    let expected: Vec<f32> = [a, b, c]
                        .iter()
                        .enumerate()
                        .flat_map(|(h, e)| {
                            data[(h * entries + e) * 2..(h * entries + e) * 2 + 2]
                                .iter()
                                .copied()
                        })
                        .collect();
                    assert_eq!(
                        book.decode_overall(1, 1, &[overall as u64]).unwrap().data(),
                        expected
                    );
                    assert_eq!(
                        book.decode_heads(1, 1, &[a, b, c]).unwrap().data(),
                        expected
                    );
                }
            }
        }
    }
}

#[test]
fn output_limit_and_invalid_shape_do_not_allocate_large_output() {
    let book = Codebook::new(1, 2, 256, vec![0.; 512]).unwrap();
    let rows = MAX_ELEMENTS / 256 + 1;
    assert!(matches!(
        book.decode_overall(1, rows, &vec![0; rows]),
        Err(Error::Limit)
    ));
    assert!(matches!(
        book.decode_heads(1, rows, &vec![0; rows]),
        Err(Error::Limit)
    ));
    assert!(matches!(
        book.decode_overall(usize::MAX, 2, &[]),
        Err(Error::Limit)
    ));
    assert!(matches!(book.decode_overall(1, 2, &[0]), Err(Error::Shape)));
    assert!(matches!(book.decode_heads(1, 0, &[]), Err(Error::Shape)));
    assert!(matches!(Codebook::new(0, 1, 1, vec![]), Err(Error::Shape)));
    assert!(matches!(
        Codebook::new(1, 2, 1, vec![0.]),
        Err(Error::Shape)
    ));
}

#[test]
fn copying_preserves_fp32_bits_and_batch_order() {
    let data = vec![-0.0, f32::from_bits(1), f32::MAX, -f32::MAX];
    let book = Codebook::new(1, 2, 2, data.clone()).unwrap();
    for _ in 0..100 {
        let decoded = book.decode_overall(2, 2, &[1, 0, 0, 1]).unwrap();
        let expected = [
            data[2], data[3], data[0], data[1], data[0], data[1], data[2], data[3],
        ];
        assert_eq!(
            decoded
                .data()
                .iter()
                .map(|x| x.to_bits())
                .collect::<Vec<_>>(),
            expected.iter().map(|x| x.to_bits()).collect::<Vec<_>>()
        );
    }
}
